from pathlib import Path
import ipaddress,random,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'scripts'))
from ranges import merge,intersection,subtract,cidrs

class RangesTest(unittest.TestCase):
    def test_exact_ipv4_split(self):
        self.assertEqual([str(n) for n in cidrs(subtract([(0,255)],[(64,127)]),4)],['0.0.0.0/26','0.0.0.128/25'])
    def test_ipv6_endpoint_and_split(self):
        maximum=2**128-1
        self.assertEqual(subtract([(0,maximum)],[(0,0),(maximum,maximum)]),[(1,maximum-1)])
        self.assertEqual(sum(n.num_addresses for n in cidrs([(maximum-255,maximum)],6)),256)
    def test_adjacency_and_empty(self):
        self.assertEqual(merge([(10,20),(0,9),(18,30)]),[(0,30)])
        self.assertEqual(intersection([],[(0,1)]),[])
        self.assertEqual(subtract([(0,7)],[(0,7)]),[])
    def test_random_against_finite_set_oracle(self):
        rng=random.Random(311)
        def expand(rs): return {n for a,b in rs for n in range(a,b+1)}
        for _ in range(200):
            a=merge([tuple(sorted([rng.randrange(128),rng.randrange(128)])) for _ in range(5)])
            b=merge([tuple(sorted([rng.randrange(128),rng.randrange(128)])) for _ in range(5)])
            self.assertEqual(expand(intersection(a,b)),expand(a)&expand(b))
            self.assertEqual(expand(subtract(a,b)),expand(a)-expand(b))

if __name__=='__main__': unittest.main()
