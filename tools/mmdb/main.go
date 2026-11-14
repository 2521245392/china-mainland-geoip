package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"os"

	"github.com/maxmind/mmdbwriter"
	"github.com/maxmind/mmdbwriter/mmdbtype"
	maxminddb "github.com/oschwald/maxminddb-golang"
)

type Row struct {
	CIDR   string         `json:"cidr"`
	Record map[string]any `json:"record"`
}

func check(err error) {
	if err != nil {
		log.Fatal(err)
	}
}

func convert(value any) mmdbtype.DataType {
	switch v := value.(type) {
	case map[string]any:
		out := mmdbtype.Map{}
		for k, item := range v {
			out[mmdbtype.String(k)] = convert(item)
		}
		return out
	case string:
		return mmdbtype.String(v)
	case bool:
		return mmdbtype.Bool(v)
	default:
		log.Fatalf("unsupported payload type %T; refusing a lossy conversion", value)
		return nil
	}
}

func dump(path, target string) {
	db, err := maxminddb.Open(path)
	check(err)
	defer db.Close()
	check(db.Verify())
	out, err := os.Create(target)
	check(err)
	writer := bufio.NewWriter(out)
	encoder := json.NewEncoder(writer)
	networks := db.Networks(maxminddb.SkipAliasedNetworks)
	count := 0
	for networks.Next() {
		record := map[string]any{}
		network, err := networks.Network(&record)
		check(err)
		check(encoder.Encode(Row{network.String(), record}))
		count++
	}
	check(networks.Err())
	check(writer.Flush())
	check(out.Close())
	metadata, err := json.MarshalIndent(db.Metadata, "", "  ")
	check(err)
	check(os.WriteFile(target+".metadata.json", append(metadata, '\n'), 0644))
	fmt.Printf("Dumped and structurally verified %d networks from %s\n", count, path)
}

func build(original, rows, target string) {
	raw, err := os.ReadFile(original)
	check(err)
	var meta maxminddb.Metadata
	check(json.Unmarshal(raw, &meta))
	tree, err := mmdbwriter.New(mmdbwriter.Options{
		BuildEpoch: int64(meta.BuildEpoch), DatabaseType: meta.DatabaseType,
		Description: meta.Description, IPVersion: int(meta.IPVersion),
		Languages: meta.Languages, RecordSize: int(meta.RecordSize),
		IncludeReservedNetworks: true,
	})
	check(err)
	input, err := os.Open(rows)
	check(err)
	defer input.Close()
	scanner := bufio.NewScanner(input)
	scanner.Buffer(make([]byte, 4096), 1024*1024)
	count := 0
	for scanner.Scan() {
		var row Row
		check(json.Unmarshal(scanner.Bytes(), &row))
		_, network, err := net.ParseCIDR(row.CIDR)
		check(err)
		check(tree.Insert(network, convert(row.Record)))
		count++
	}
	check(scanner.Err())
	file, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0644)
	check(err)
	_, err = tree.WriteTo(file)
	check(err)
	check(file.Close())
	fmt.Printf("Rebuilt %s from %d CIDR inserts; original record schema and metadata retained\n", target, count)
}

func lookup(path, inputPath, outputPath string) {
	db, err := maxminddb.Open(path)
	check(err)
	defer db.Close()
	input, err := os.Open(inputPath)
	check(err)
	defer input.Close()
	output, err := os.Create(outputPath)
	check(err)
	scanner := bufio.NewScanner(input)
	encoder := json.NewEncoder(output)
	count := 0
	for scanner.Scan() {
		row := map[string]any{}
		check(json.Unmarshal(scanner.Bytes(), &row))
		ip := net.ParseIP(row["ip"].(string))
		if ip == nil {
			log.Fatal("invalid sample IP")
		}
		var record map[string]any
		check(db.Lookup(ip, &record))
		label := "NONE"
		if record != nil {
			country, ok := record["country"].(map[string]any)
			if !ok {
				log.Fatal("unexpected record schema")
			}
			label = country["iso_code"].(string)
		}
		if label != row["expected"] {
			log.Fatalf("sample mismatch: %s expected=%s actual=%s", ip, row["expected"], label)
		}
		row["actual"] = label
		row["actual_record"] = record
		row["result"] = "PASS"
		check(encoder.Encode(row))
		count++
	}
	check(scanner.Err())
	check(output.Close())
	fmt.Printf("Validated %d sampled address lookups\n", count)
}

func main() {
	if len(os.Args) == 5 && os.Args[1] == "lookup" {
		lookup(os.Args[2], os.Args[3], os.Args[4])
		return
	}
	if len(os.Args) == 4 && os.Args[1] == "dump" {
		dump(os.Args[2], os.Args[3])
		return
	}
	if len(os.Args) == 5 && os.Args[1] == "build" {
		build(os.Args[2], os.Args[3], os.Args[4])
		return
	}
	log.Fatal("usage: processor dump input.mmdb output.jsonl | processor build original.mmdb filtered.jsonl output.mmdb")
}
