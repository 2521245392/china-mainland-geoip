"""Exact IPv4/IPv6 interval arithmetic; endpoints are inclusive."""
from pathlib import Path
import ipaddress,bisect

def addr(value,version):
    return (ipaddress.IPv4Address if version==4 else ipaddress.IPv6Address)(value)

def merge(ranges):
    out=[]
    for a,b in sorted(ranges):
        if out and a<=out[-1][1]+1: out[-1]=(out[-1][0],max(b,out[-1][1]))
        else: out.append((a,b))
    return out

def load_cidrs(path,version=None):
    out={4:[],6:[]}
    for line in Path(path).read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        net=ipaddress.ip_network(line)
        assert version is None or net.version==version,(path,line)
        out[net.version].append((int(net.network_address),int(net.broadcast_address)))
    return {v:merge(rs) for v,rs in out.items()}

def intersection(a,b):
    i=j=0; out=[]
    while i<len(a) and j<len(b):
        lo=max(a[i][0],b[j][0]); hi=min(a[i][1],b[j][1])
        if lo<=hi: out.append((lo,hi))
        if a[i][1]<b[j][1]: i+=1
        else: j+=1
    return merge(out)

def subtract(a,b):
    out=[]; j=0
    for lo,hi in a:
        while j<len(b) and b[j][1]<lo: j+=1
        cursor=lo; k=j
        while k<len(b) and b[k][0]<=hi:
            x,y=b[k]
            if cursor<x: out.append((cursor,min(hi,x-1)))
            cursor=max(cursor,y+1)
            if cursor>hi: break
            k+=1
        if cursor<=hi: out.append((cursor,hi))
    return merge(out)

def total(ranges): return sum(b-a+1 for a,b in ranges)

def cidrs(ranges,version):
    for a,b in ranges:
        yield from ipaddress.summarize_address_range(addr(a,version),addr(b,version))

def overlaps(ranges,lo,hi):
    ends=[b for a,b in ranges]
    pos=bisect.bisect_left(ends,lo)
    result=[]
    while pos<len(ranges) and ranges[pos][0]<=hi:
        a,b=ranges[pos]; result.append((max(a,lo),min(b,hi))); pos+=1
    return result

def read_regions(path):
    previous=-1
    with Path(path).open(encoding="utf-8-sig") as handle:
        for raw in handle:
            if not raw.strip() or raw.lstrip().startswith("#"): continue
            fields=raw.rstrip("\r\n").split("|")
            if len(fields)!=7: raise ValueError("Expected seven ip2region fields")
            a,b=(int(ipaddress.ip_address(value)) for value in fields[:2])
            if not previous<a<=b: raise ValueError("Overlapping or unsorted ip2region input")
            previous=b
            yield a,b,"|".join(fields[2:])
