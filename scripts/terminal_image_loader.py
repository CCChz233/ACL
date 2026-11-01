"""Import a frozen public Docker image through host curl and an OCI archive."""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work/terminal-round1'
BASE=ROOT/'work/terminal-pilot-v1'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return 'sha256:'+h.hexdigest()


def load(task_id,tag=None,base_repo=None):
    cfg=json.loads((ROOT/'configs/terminal-round1.json').read_text())
    task=next(t for t in cfg['tasks'] if t['id']==task_id)
    image=task['image'];repo=image.rsplit(':',1)[0]
    original=json.loads((BASE/'image-pulls'/f'baseline-{task_id}.json').read_text())
    expected=original['Id'];tag=tag or image
    cache=WORK/'image-transfer-cache';blobs=cache/'blobs/sha256';blobs.mkdir(parents=True,exist_ok=True)
    logs=WORK/'image-transfer-logs';logs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
        temp=Path(tmp)
        def get(url,path,header=None,seconds=300):
            cmd=['curl','--http1.1','--silent','--show-error','--fail','--location','--retry','3','--retry-all-errors',
                 '--connect-timeout','15','--max-time',str(seconds),'--output',str(path)]
            if header:cmd+=['--header','@'+str(header)]
            r=subprocess.run([*cmd,url],capture_output=True,text=True)
            if r.returncode:raise RuntimeError(f'Public image download failed: curl code {r.returncode}')
        get(f'https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull',temp/'token.json',seconds=60)
        token=json.loads((temp/'token.json').read_text())['token']
        header=temp/'headers';header.write_text('Authorization: Bearer '+token+'\nAccept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json\n');os.chmod(header,0o600)
        manifests={}
        def manifest(ident):
            path=blobs/ident.split(':')[1]
            if not path.exists():get(f'https://registry-1.docker.io/v2/{repo}/manifests/{ident}',path,header)
            if digest(path)!=ident:raise ValueError('Manifest digest mismatch')
            data=json.loads(path.read_text());manifests[ident]=data
            return data
        top=manifest(expected);actual=top
        if 'manifests' in top:
            children=[m for m in top['manifests'] if m.get('platform',{}).get('os')=='linux' and m.get('platform',{}).get('architecture')=='amd64']
            if len(children)!=1:raise ValueError('Ambiguous platform')
            actual=manifest(children[0]['digest'])
        descriptors=[actual['config'],*actual['layers']]
        alternate_header=None
        if base_repo:
            get(f'https://auth.docker.io/token?service=registry.docker.io&scope=repository:{base_repo}:pull',temp/'base-token.json',seconds=60)
            base_token=json.loads((temp/'base-token.json').read_text())['token']
            alternate_header=temp/'base-headers';alternate_header.write_text('Authorization: Bearer '+base_token+'\n');os.chmod(alternate_header,0o600)
        needed=sum(d['size'] for d in descriptors if not (blobs/d['digest'].split(':')[1]).exists())
        if shutil.disk_usage(ROOT).free < cfg['min_free_bytes']+needed+original['Size']:
            raise RuntimeError('Insufficient disk for safe image import')
        def blob(desc):
            path=blobs/desc['digest'].split(':')[1]
            if path.exists() and digest(path)==desc['digest']:return
            partial=path.with_suffix('.partial')
            print(f'download {task_id} {desc["digest"][:23]} bytes={desc["size"]}',flush=True)
            source_repo=base_repo if base_repo and desc['digest']==actual['layers'][0]['digest'] else repo
            source_header=alternate_header if source_repo==base_repo else header
            get(f'https://registry-1.docker.io/v2/{source_repo}/blobs/{desc["digest"]}',partial,source_header,seconds=600)
            if digest(partial)!=desc['digest']:raise ValueError('Image blob digest mismatch')
            partial.replace(path)
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(blob,descriptors))
        top_path=blobs/expected.split(':')[1]
        index={'schemaVersion':2,'mediaType':'application/vnd.oci.image.index.v1+json','manifests':[{
            'mediaType':top['mediaType'],'digest':expected,'size':top_path.stat().st_size,
            'annotations':{'io.containerd.image.name':tag,'org.opencontainers.image.ref.name':tag}}]}
        include={expected,*manifests,*[d['digest'] for d in descriptors]}
        with (logs/f'{task_id}-load.log').open('w') as out:
            process=subprocess.Popen(['docker','image','load','--platform','linux/amd64'],stdin=subprocess.PIPE,stdout=out,stderr=subprocess.STDOUT)
            try:
                with tarfile.open(fileobj=process.stdin,mode='w|') as archive:
                    for name,data in [('oci-layout',{'imageLayoutVersion':'1.0.0'}),('index.json',index)]:
                        raw=json.dumps(data).encode();info=tarfile.TarInfo(name);info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
                    for ident in sorted(include):
                        file=blobs/ident.split(':')[1];archive.add(file,arcname='blobs/sha256/'+file.name)
                process.stdin.close()
                if process.wait():raise RuntimeError('OCI image import failed; see local load log')
            except BaseException:
                process.stdin.close();process.wait();raise
        inspect=subprocess.run(['docker','image','inspect',tag],capture_output=True,text=True)
        if inspect.returncode:
            subprocess.run(['docker','tag',expected,tag],check=True,capture_output=True)
            inspect=subprocess.run(['docker','image','inspect',tag],check=True,capture_output=True,text=True)
        loaded=json.loads(inspect.stdout)[0]
        if loaded['Id']!=expected:raise ValueError('Imported image differs from baseline')
        (logs/f'{task_id}-manifest.json').write_text(json.dumps({'canonical_image':image,'loaded_tag':tag,'expected_id':expected,
            'loaded_id':loaded['Id'],'blob_digests':[d['digest'] for d in descriptors],
            'base_blob_source_repo':base_repo,
            'transport':'official Registry via host curl, OCI import preserving manifest digest'},indent=2)+'\n')
        print('Loaded and verified '+tag+' '+expected,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('task');p.add_argument('--tag');p.add_argument('--base-repo');args=p.parse_args();load(args.task,args.tag,args.base_repo)
