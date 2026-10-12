"""Inspect every Git object and publishable working file without printing secrets.

Heuristic checks supplement manual review; findings show location and rule only.
Uses the standard library and Git, so it also runs before dependencies are installed.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parent
RULES={
    'absolute_drive_path':re.compile(r'(?i)\b[a-z]:[\\/]'),
    'home_path':re.compile(r'(?i)(?:/Users/|/home/)[a-z0-9_.-]+/'),
    'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'github_token':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'openai_token':re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}\b'),
    'aws_access_key':re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'slack_token':re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
    'credential_url':re.compile(r'https?://[^\s/:]+:[^\s/@]+@'),
    'assigned_secret':re.compile(r'''(?i)(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)\s*[:=]\s*["'][A-Za-z0-9_+/=-]{20,}["']'''),
}
DATA_EXT={'.csv','.parquet','.xlsx','.xls','.hgt','.gz','.zip','.tif','.tiff','.geojson',
          '.pdf','.png','.hwpx','.hwp','.sqlite','.db','.bundle','.pem','.key'}


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)


def check_text(data,location,findings):
    try: s=data.decode('utf8')
    except UnicodeDecodeError:
        findings.append({'location':location,'rule':'non_text_blob'});return
    if '\x00' in s:findings.append({'location':location,'rule':'binary_blob'})
    for rule,pattern in RULES.items():
        for match in pattern.finditer(s):
            findings.append({'location':location,'line':s.count('\n',0,match.start())+1,'rule':rule})


def inspect():
    findings=[]
    # All stored objects, including unreachable ones, not just the current branch.
    objects=git('cat-file','--batch-all-objects','--batch-check=%(objectname) %(objecttype) %(objectsize)').decode().splitlines()
    max_blob=0;blob_count=0
    for line in objects:
        oid,kind,size=line.split();size=int(size)
        if kind=='blob':
            blob_count+=1;max_blob=max(max_blob,size)
            if size>1024*1024:findings.append({'location':oid[:12],'rule':'blob_over_1MiB','bytes':size})
        if kind in ['blob','commit','tag']:
            check_text(git('cat-file',kind,oid),f'{kind}:{oid[:12]}',findings)
    commits=git('rev-list','--all').decode().splitlines()
    historical_paths=set()
    for oid in commits:
        for item in git('ls-tree','-rz','--full-tree',oid).split(b'\0'):
            if not item:continue
            name=item.split(b'\t',1)[1].decode('utf8')
            historical_paths.add(name)
            if Path(name).suffix.lower() in DATA_EXT:
                findings.append({'location':f'{oid[:12]}:{name}','rule':'data_or_generated_file'})
            if '.env' in Path(name).name and Path(name).name!='.env.example':
                findings.append({'location':f'{oid[:12]}:{name}','rule':'environment_file'})
    names=git('ls-files','-z','--cached','--others','--exclude-standard').split(b'\0')
    current=[]
    for name in sorted(set(names)):
        if not name:continue
        rel=name.decode('utf8');p=ROOT/rel
        if not p.is_file():continue
        current.append(rel)
        if p.stat().st_size>1024*1024:findings.append({'location':rel,'rule':'file_over_1MiB'})
        if p.suffix.lower() in DATA_EXT:findings.append({'location':rel,'rule':'data_or_generated_file'})
        check_text(p.read_bytes(),rel,findings)
    check_text((ROOT/'.git'/'config').read_bytes(),'local_git_config',findings)
    return {'status':'passed' if not findings else 'failed','commits':len(commits),
            'all_objects':len(objects),'blobs':blob_count,'max_blob_bytes':max_blob,
            'historical_paths':sorted(historical_paths),'public_files':current,
            'findings':findings,'limitations':'Pattern-based scan; cannot prove absence of every possible secret or future accidental commit.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--json',type=Path);a=p.parse_args()
    result=inspect()
    if a.json:
        a.json.parent.mkdir(parents=True,exist_ok=True)
        a.json.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['status']=='passed' else 1)
