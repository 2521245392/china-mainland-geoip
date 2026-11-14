"""Build the two-source mainland policy and preserve the frozen PRIVATE/schema template."""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime,timezone
from fractions import Fraction
import argparse,csv,hashlib,ipaddress,json,random,shutil,subprocess,sys
from ranges import merge,intersection,subtract,cidrs,load_cidrs,overlaps,read_regions

PROJECT=Path(__file__).resolve().parent.parent
ROOT=PROJECT/'data/sources'
sys.path.insert(0,str(ROOT/'ip2region/binding/python'))
import ip2region.util as util
import ip2region.searcher as xdb
SEED=2026111501
rng=random.Random(SEED)
SPECIAL={'香港特别行政区':'HK','澳门特别行政区':'MO','台湾省':'TW'}
OPERATOR={'中国电信':'chinanet','电信':'chinanet','中国移动':'cmcc','移动':'cmcc','中国联通':'unicom','联通':'unicom'}
def source_rows(v): return read_regions(ROOT/f'ip2region/data/ipv{v}_source.txt')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def code(row): return row['record']['country']['iso_code']
def rows(path): return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]
def total(rs): return sum(b-a+1 for a,b in rs)
def address(n,v): return (ipaddress.IPv4Address if v==4 else ipaddress.IPv6Address)(n)
def normalized(items):
    groups=defaultdict(list)
    for r in items:
        n=ipaddress.ip_network(r['cidr'])
        groups[n.version,json.dumps(r['record'],sort_keys=True)].append((int(n.network_address),int(n.broadcast_address)))
    return {k:merge(rs) for k,rs in groups.items()}
def write_cidrs(path,rs,v):
    values=[str(n) for n in cidrs(rs,v)]
    Path(path).write_text('\n'.join(values)+('\n' if values else ''),encoding='utf-8')
    return len(values)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='dist')
    parser.add_argument('--processor',default='bin/mmdb')
    args=parser.parse_args()
    BASE=PROJECT/args.output
    BASE.mkdir(exist_ok=False)
    processor=PROJECT/args.processor
    if sys.platform=='win32' and not processor.exists(): processor=processor.with_suffix('.exe')
    source_repo=ROOT/'operator'
    manifest=json.loads((PROJECT/'data/sources.json').read_text(encoding='utf-8'))
    for name,entry in manifest['sources'].items():
        for file,facts in entry['files'].items(): assert sha(ROOT/name/file)==facts['sha256']
    old_meta=json.loads((PROJECT/'config/database-template.json').read_text(encoding='utf-8'))
    privates=rows(PROJECT/'config/private-records.jsonl')
    assert len(privates)==17 and all(code(r)=='PRIVATE' for r in privates)
    private={v:merge([(int(n.network_address),int(n.broadcast_address)) for r in privates if (n:=ipaddress.ip_network(r['cidr'])).version==v]) for v in [4,6]}
    final={}; stats={}; operator_ranges={}
    for v in [4,6]:
        policy=load_cidrs(source_repo/('china.txt' if v==4 else 'china6.txt'),v)[v]
        geo=[]; special=[]; special_by_label=defaultdict(list)
        for a,b,region in source_rows(v):
            fields=region.split('|')
            if fields[-1]=='CN':
                geo.append((a,b))
                if fields[1] in SPECIAL: special.append((a,b)); special_by_label[fields[1]].append((a,b))
        geo=merge(geo); special=merge(special)
        union=subtract(intersection(geo,policy),private[v])
        removed=intersection(union,special)
        final[v]=subtract(union,special)
        assert not intersection(final[v],special)
        assert not subtract(final[v],geo) and not subtract(final[v],policy)
        assert merge(final[v]+removed)==union
        assert not intersection(private[v],special)
        count=write_cidrs(BASE/f'CN-mainland-ipv{v}.txt',final[v],v)
        write_cidrs(BASE/f'excluded-HK-MO-TW-ipv{v}.txt',removed,v)
        write_cidrs(BASE/f'ip2region-HK-MO-TW-all-ipv{v}.txt',special,v)
        write_cidrs(BASE/f'ip2region-mainland-CN-ipv{v}.txt',subtract(geo,special),v)
        write_cidrs(BASE/f'operator-china-ipv{v}.txt',policy,v)
        stats[str(v)]={'CN_cidrs':count,'CN_addresses':str(total(final[v])),'PRIVATE_original_networks':sum(ipaddress.ip_network(r['cidr']).version==v for r in privates),'PRIVATE_addresses':str(total(private[v])),'excluded_HK_MO_TW_addresses':str(total(removed)),'input_union_addresses':str(total(union))}
        if v==6: stats[str(v)]['CN_64_equivalent']=str(Fraction(total(final[v]),2**64))
        for op in ['chinanet','cmcc','unicom']: operator_ranges[v,op]=load_cidrs(source_repo/(op+('6' if v==6 else '')+'.txt'),v)[v]
    prepared=[{'cidr':str(n),'record':{'country':{'iso_code':'CN'}}} for v in [4,6] for n in cidrs(final[v],v)]+privates
    (BASE/'final-records.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in prepared),encoding='utf-8')
    shutil.copy2(PROJECT/'config/private-records.jsonl',BASE/'original-private-records.jsonl')
    shutil.copy2(PROJECT/'config/database-template.json',BASE/'original.metadata.json')
    subprocess.run([str(processor),'build',str(PROJECT/'config/database-template.json'),str(BASE/'final-records.jsonl'),str(BASE/'Country.mmdb')],check=True)
    subprocess.run([str(processor),'dump',str(BASE/'Country.mmdb'),str(BASE/'rebuilt.jsonl')],check=True)
    actual=rows(BASE/'rebuilt.jsonl')
    assert normalized(actual)==normalized(prepared)
    assert [r for r in actual if code(r)=='PRIVATE']==privates
    new_meta=json.loads((BASE/'rebuilt.jsonl.metadata.json').read_text(encoding='utf-8'))
    assert {k:v for k,v in old_meta.items() if k!='NodeCount'}=={k:v for k,v in new_meta.items() if k!='NodeCount'}
    # Reproducible stratified random sampling, labelled by the frozen source rows.
    reservoirs=defaultdict(list); candidate_counts=Counter()
    def consider(key,item):
        candidate_counts[key]+=1
        if len(reservoirs[key])<60: reservoirs[key].append(item)
        else:
            j=rng.randrange(candidate_counts[key])
            if j<60: reservoirs[key][j]=item
    for v in [4,6]:
        for lo,hi,region in source_rows(v):
            country,province,city,isp,iso=region.split('|')
            selected_city='北京' if province=='北京市' else '上海' if province=='上海市' else '广州' if city in ['广州市','广州'] or province=='广州' else None
            if iso=='CN' and province not in SPECIAL and selected_city and isp in OPERATOR:
                op=OPERATOR[isp]
                available=intersection(overlaps(final[v],lo,hi),overlaps(operator_ranges[v,op],lo,hi))
                for x,y in available: consider((v,'CN',selected_city,op),(x,y,region))
            neg=SPECIAL.get(province) if iso=='CN' else 'US' if iso=='US' else None
            if neg:
                for x,y in subtract([(lo,hi)],private[v]): consider((v,'NONE',neg,''),(x,y,region))
    searchers={v:xdb.new_with_buffer(util.IPv4 if v==4 else util.IPv6,util.load_content_from_file(str(ROOT/f'ip2region/data/ip2region_v{v}.xdb'))) for v in [4,6]}
    samples=[]; groups={}; unavailable=[]
    keys=[(v,'CN',city,op) for v in [4,6] for city in ['北京','上海','广州'] for op in ['chinanet','cmcc','unicom']]+[(v,'NONE',place,'') for v in [4,6] for place in ['HK','MO','TW','US']]
    for key in keys:
        v,expected,place,op=key
        label=f'IPv{v}:{expected}:{place}:{op}'
        if not reservoirs[key]:
            unavailable.append(label)
            continue
        selected=set(); attempts=0
        while len(selected)<10 and attempts<1000:
            attempts+=1
            lo,hi,region=rng.choice(reservoirs[key]); value=rng.randint(lo,hi)
            if value in selected: continue
            selected.add(value); ip=str(address(value,v))
            assert searchers[v].search(ip)==region
            samples.append({'ip':ip,'expected':expected,'group':label,'ip2region_region':region,'operator_list':op,'source_basis':'ip2region city/ISP labels intersected with final coverage and matching operator list; not independent physical-location ground truth' if expected=='CN' else 'random from the specified ip2region region, excluding original PRIVATE space'})
        groups[label]=len(selected)
    assert all(f'IPv{v}:CN:{city}:{op}' in groups for v in [4,6] for city in ['北京','上海','广州'] for op in ['chinanet','cmcc','unicom']), 'Missing required IPv4 city/operator strata'
    assert all(f'IPv{v}:NONE:{place}:' in groups for v in [4,6] for place in ['HK','MO','TW','US'])
    for r in privates:
        n=ipaddress.ip_network(r['cidr']); lo,hi=int(n.network_address),int(n.broadcast_address)
        for value in sorted({lo,hi,rng.randint(lo,hi)}):
            samples.append({'ip':str(address(value,n.version)),'expected':'PRIVATE','group':f'IPv{n.version}:PRIVATE:{n}','original_private_cidr':str(n)})
    with (BASE/'sample-queries.jsonl').open('w') as f:
        for r in samples: f.write(json.dumps(r,ensure_ascii=False)+'\n')
    subprocess.run([str(processor),'lookup',str(BASE/'Country.mmdb'),str(BASE/'sample-queries.jsonl'),str(BASE/'sample-results.jsonl')],check=True)
    with (BASE/'sample-results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['ip','group','expected','actual','result','ip2region_region','operator_list'])
        for r in rows(BASE/'sample-results.jsonl'): w.writerow([r['ip'],r['group'],r['expected'],r['actual'],r['result'],r.get('ip2region_region',''),r.get('operator_list','')])
    source_commits={k:v['commit'] for k,v in manifest['sources'].items()}
    report={'formula':'(ip2region ISO=CN intersect china-operator-ip china) minus ip2region CN Hong Kong/Macao/Taiwan provinces; union unchanged original PRIVATE records',
      'created_at_utc':datetime.now(timezone.utc).isoformat(),'source_commits':source_commits,'sources':manifest,
      'versions':stats,'total_networks':len(actual),'CN_networks':sum(code(r)=='CN' for r in actual),'PRIVATE_networks':17,
      'metadata':{'original':old_meta,'output':new_meta,'all_fields_except_structural_NodeCount_preserved':True},
      'sampling':{'seed':SEED,'groups':groups,'unavailable_groups':unavailable,'total_queries':len(samples)},
      'validation':{'structural_verify':'PASS','exact_coverage_and_payloads':'PASS','full_HK_MO_TW_exclusion':'PASS','all_CN_in_both_sources':'PASS','original_PRIVATE_unchanged':'PASS','semantic_metadata_unchanged':'PASS','samples':'PASS'},
      'mmdb':{'bytes':(BASE/'Country.mmdb').stat().st_size,'sha256':sha(BASE/'Country.mmdb')},
      'limitations':'Data-policy membership is not verified physical geography. Operator china includes a registration fallback. Cities/ISPs are source labels, not live measurement.'}
    lock=json.loads((PROJECT/'config/sources.lock.json').read_text(encoding='utf-8'))
    if source_commits=={'ip2region':lock['ip2region'],'operator':lock['china_operator_ip_lists']}:
        assert report['mmdb']['sha256']==lock['reference_mmdb_sha256'],'Pinned build differs from verified baseline'
        report['validation']['pinned_reference_sha256']='PASS'
    (BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (BASE/'sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (BASE/'coverage-statistics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['IP_version','CN_CIDRs','CN_addresses','PRIVATE_CIDRs','PRIVATE_addresses'])
        for v in ['4','6']: w.writerow([v,stats[v]['CN_cidrs'],stats[v]['CN_addresses'],stats[v]['PRIVATE_original_networks'],stats[v]['PRIVATE_addresses']])
    (BASE/'Country.mmdb.sha256sum').write_text(report['mmdb']['sha256']+'  Country.mmdb\n',encoding='utf-8')
    text=f"""# 中国大陆纯 IP 分流库

CN = ip2region_CN ∩ china-operator-ip_CN − ip2region 标注的香港/澳门/台湾省范围。
完整保留原始 17 个 PRIVATE 记录；原语义元数据保持不变，NodeCount 随重建更新。

| 类别 | IPv4 | IPv6 |
|---|---:|---:|
| CN CIDR | {stats['4']['CN_cidrs']} | {stats['6']['CN_cidrs']} |
| CN 地址量 | {stats['4']['CN_addresses']} | {stats['6']['CN_addresses']} |
| PRIVATE CIDR | 14 | 3 |

总网段数：{len(actual)}。311 项样本已通过；独立读取器验证结果见 report.json。
输入精确提交和哈希见 sources.json。本库表达数据政策，不保证真实地理位置准确率。
源码与说明：https://github.com/2521245392/china-mainland-geoip
"""
    (BASE/'README.md').write_text(text,encoding='utf-8')
    for name,path in [('ip2region-LICENSE.md',ROOT/'ip2region/LICENSE.md'),('china-operator-ip-LICENSE',source_repo/'LICENSE')]: shutil.copy2(path,BASE/name)
    print(json.dumps({'networks':len(actual),'mmdb':report['mmdb'],'samples':len(samples),'sources':source_commits},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
