"""Independent libmaxminddb reader plus complete interval and schema verification."""
from pathlib import Path
import argparse,hashlib,ipaddress,json
import maxminddb
from ranges import merge,load_cidrs,intersection,subtract

ROOT=Path(__file__).resolve().parent.parent
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default='dist'); args=parser.parse_args()
    out=ROOT/args.output
    report=json.loads((out/'report.json').read_text(encoding='utf-8'))
    private=[json.loads(line) for line in (ROOT/'config/private-records.jsonl').read_text(encoding='utf-8').splitlines()]
    template=json.loads((ROOT/'config/database-template.json').read_text(encoding='utf-8'))
    lookups=0
    with maxminddb.open_database(str(out/'Country.mmdb')) as db:
        actual=list(db)
        assert len(actual)==report['total_networks']
        actual_private=[{'cidr':str(n),'record':r} for n,r in actual if r['country']['iso_code']=='PRIVATE']
        assert actual_private==private
        keys={'database_type':'DatabaseType','languages':'Languages','description':'Description','build_epoch':'BuildEpoch','ip_version':'IPVersion','record_size':'RecordSize','binary_format_major_version':'BinaryFormatMajorVersion','binary_format_minor_version':'BinaryFormatMinorVersion'}
        for key,source_key in keys.items(): assert getattr(db.metadata(),key)==template[source_key],key
        for v in [4,6]:
            cn=merge([(int(n.network_address),int(n.broadcast_address)) for n,r in actual if n.version==v and r['country']['iso_code']=='CN'])
            prv=merge([(int(n.network_address),int(n.broadcast_address)) for r in private if (n:=ipaddress.ip_network(r['cidr'])).version==v])
            mainland=load_cidrs(out/f'ip2region-mainland-CN-ipv{v}.txt',v)[v]
            special=load_cidrs(out/f'ip2region-HK-MO-TW-all-ipv{v}.txt',v)[v]
            policy=load_cidrs(out/f'operator-china-ipv{v}.txt',v)[v]
            assert cn==subtract(intersection(mainland,policy),prv)
            assert not intersection(cn,special) and not intersection(prv,special)
            assert sum(b-a+1 for a,b in cn)==int(report['versions'][str(v)]['CN_addresses'])
        for n,r in actual:
            assert r in [{'country':{'iso_code':'CN'}},{'country':{'iso_code':'PRIVATE'}}]
            cls=ipaddress.IPv4Address if n.version==4 else ipaddress.IPv6Address
            first,last=int(n.network_address),int(n.broadcast_address)
            for value in {first,(first+last)//2,last}:
                assert db.get(str(cls(value)))==r; lookups+=1
        samples=[json.loads(line) for line in (out/'sample-results.jsonl').read_text(encoding='utf-8').splitlines()]
        assert len(samples)==311
        for sample in samples:
            expected=None if sample['expected']=='NONE' else {'country':{'iso_code':sample['expected']}}
            assert db.get(sample['ip'])==expected
            assert sample['actual']==sample['expected'] and sample['result']=='PASS'
            lookups+=1
    report['independent_validation']={'reader':'Python maxminddb/libmaxminddb','full_set_formula':'PASS','HK_MO_TW_overlap':'NONE','PRIVATE_and_schema':'PASS','semantic_metadata':'PASS','samples':'PASS','total_lookups':lookups}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert hashlib.sha256((out/'Country.mmdb').read_bytes()).hexdigest()==report['mmdb']['sha256']
    files=[p for p in sorted(out.iterdir()) if p.is_file() and p.name!='SHA256SUMS']
    (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files),encoding='utf-8')
    print(f'PASS: exact coverage, metadata, 17 PRIVATE records and {lookups} independent lookups')

if __name__=='__main__': main()
