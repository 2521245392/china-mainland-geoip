"""Resolve each upstream once, then record the immutable commits and input hashes."""
from pathlib import Path
import argparse,hashlib,json,subprocess

ROOT=Path(__file__).resolve().parent.parent
def run(*args): return subprocess.check_output(args,text=True).strip()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['latest','pinned'],default='latest')
    args=parser.parse_args()
    lock=json.loads((ROOT/'config/sources.lock.json').read_text(encoding='utf-8'))
    destination=ROOT/'data/sources'
    destination.mkdir(parents=True,exist_ok=True)
    specs=[('ip2region','https://github.com/lionsoul2014/ip2region.git','master','ip2region',['data/ipv4_source.txt','data/ipv6_source.txt','data/ip2region_v4.xdb','data/ip2region_v6.xdb']),('operator','https://github.com/gaoyifan/china-operator-ip.git','ip-lists','china_operator_ip_lists',['china.txt','china6.txt','chinanet.txt','chinanet6.txt','cmcc.txt','cmcc6.txt','unicom.txt','unicom6.txt'])]
    manifest={'mode':args.mode,'sources':{}}
    for name,url,branch,lock_key,files in specs:
        path=destination/name
        if not path.exists():
            path.mkdir()
            run('git','-C',str(path),'init','-q')
            run('git','-C',str(path),'remote','add','origin',url)
        assert run('git','-C',str(path),'remote','get-url','origin')==url,'Unexpected checkout remote'
        ref=lock[lock_key] if args.mode=='pinned' else branch
        run('git','-C',str(path),'fetch','--depth=1','origin',ref)
        run('git','-C',str(path),'checkout','--detach','--force','FETCH_HEAD')
        entry={'repository':url,'requested_ref':ref,'commit':run('git','-C',str(path),'rev-parse','HEAD'),'commit_time':run('git','-C',str(path),'log','-1','--format=%cI'),'files':{}}
        for filename in files:
            data=(path/filename).read_bytes()
            assert data,('Empty input',filename)
            entry['files'][filename]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        manifest['sources'][name]=entry
    (ROOT/'data/sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v['commit'] for k,v in manifest['sources'].items()},indent=2))

if __name__=='__main__': main()
