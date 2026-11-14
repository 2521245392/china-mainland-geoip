# China Mainland GeoIP

[![Build](https://github.com/2521245392/china-mainland-geoip/actions/workflows/build.yml/badge.svg)](https://github.com/2521245392/china-mainland-geoip/actions/workflows/build.yml)

面向代理**纯 IP 分流**的中国大陆政策库，输出 `Country.mmdb`，同时支持 IPv4、IPv6，并保留原始 17 个 `PRIVATE` 记录。

## 下载

- [Country.mmdb（固定链接）](https://github.com/2521245392/china-mainland-geoip/releases/download/latest/Country.mmdb)
- [SHA256SUMS](https://github.com/2521245392/china-mainland-geoip/releases/download/latest/SHA256SUMS)
- [校验报告 report.json](https://github.com/2521245392/china-mainland-geoip/releases/download/latest/report.json)
- [抽样明细 sample-results.csv](https://github.com/2521245392/china-mainland-geoip/releases/download/latest/sample-results.csv)
- [所有构建产物](https://github.com/2521245392/china-mainland-geoip/tree/release)
- [GitHub Actions](https://github.com/2521245392/china-mainland-geoip/actions)

也可使用 `https://raw.githubusercontent.com/2521245392/china-mainland-geoip/release/Country.mmdb` 下载。旧仓库地址不作为新构建的数据依赖。

## 筛选公式

```text
CN = (ip2region ISO=CN ∩ china-operator-ip china)
     − (ip2region ISO=CN 且省份为 香港特别行政区、澳门特别行政区、台湾省)

Country.mmdb = CN ∪ 原库全部 17 个 PRIVATE 记录
```

这等价于此前三方对比的 `(111 ∪ 011) − 指定港澳台范围`，不再要求地址已经存在于旧库，因此可以收录双方支持的新范围。执行完整整数区间交集/差集与 CIDR 拆分，不按网段首 IP 粗略判断。

所有 CN 记录保持 `{"country":{"iso_code":"CN"}}` 结构。PRIVATE 的网段和原始记录值由 `config/private-records.jsonl` 固定保存，其范围包括旧库既有的私网、保留及特殊地址，未重新定义分类。

数据库类型、描述、语言、原构建时间、IP 版本、RecordSize 和二进制格式版本按 `config/database-template.json` 保留。搜索树 `NodeCount` 随重建自动更新。**数据更新时间及实际来源版本以每次的 sources.json / report.json 为准**，不是模板中保留的 BuildEpoch。

## 自动构建与发布

参考原 `2521245392/geoip` 的定时构建、校验、Release 和 release 分支发布方式重新实现：

1. 每天北京时间 **18:30** 自动构建，也支持手动触发和 main 分支代码变更触发。
2. 默认将两个上游分支各解析成一个固定提交，本次构建只使用该快照；记录提交及所有实际输入文件的 SHA-256。
3. 生成数据库，执行完整区间、记录、元数据和抽样校验，再用独立 Python/libmaxminddb 读取器复核。
4. 仅校验成功后更新 `release` 分支和固定 `latest` Release；失败时不会发布失败产物，既有产物继续可用。

GitHub 的定时任务可能延迟。无需额外仓库 Secret，只使用发布任务的内置 `GITHUB_TOKEN`；构建任务只有仓库读取权限。此项目只构建 Country.mmdb，不包含旧流水线的 ASN 数据库下载步骤。

## 复现初次已验证版本

`config/sources.lock.json` 固定了初次版本的两个上游提交和期望数据库哈希。在 Actions 的 **Run workflow** 中选择 `pinned` 可复现该版本；日常默认 `latest` 跟随上游。

Linux 本地构建（Python 3.14、Go 版本见 tools/mmdb/go.mod）：

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/fetch_sources.py --mode pinned
mkdir -p bin
(cd tools/mmdb && go build -trimpath -o ../../bin/mmdb .)
python scripts/build.py
python scripts/verify.py
(cd dist && sha256sum --check SHA256SUMS)
```

输出目录 `dist` 必须不存在；需要第二次本地构建时使用 `--output dist-next`，并给验证程序传相同参数。上游快照在忽略提交的 `data/` 下；源码、模板和依赖锁定文件保存在仓库中。

## 校验范围

- 输出 CN 全覆盖精确等于上述集合公式，全部属于两个来源。
- 与 ip2region 全部指定港澳台范围零重叠。
- 全部 17 个 PRIVATE 原网段、原值以及语义元数据一致。
- 北京、上海、广州 × 电信、移动、联通 × IPv4/IPv6，每组 10 个，共 180 个随机样本命中 CN。
- 香港、澳门、台湾、美国 × IPv4/IPv6，每组 10 个，共 80 个随机样本未命中。
- 每个原 PRIVATE 网段的首地址、尾地址和一个随机内部地址，共 51 项命中 PRIVATE。
- 独立读取器重新查询所有 311 项样本，以及全部输出网段的边界/中点。
- 固定输入版本时，额外核对初次已验证的数据库 SHA-256。

抽样使用固定随机种子，城市和运营商身份由上游标签及对应运营商列表确定。上游缺少必需的抽样分组时构建会失败，不会悄悄降低校验标准。这不是采用外部真实位置标注集的准确率测评。

## 数据边界与授权

“中国大陆”在这里指明确的数据筛选政策，**不保证每个 IP 的物理位置或实际直连效果**。`china-operator-ip` 的 china 集合包含 BGP 分类和未宣告 RIR-CN 登记兜底；它不是纯粹的物理位置清单。Anycast、境外节点和上游数据错误仍需结合实际流量修正规则。

- [ip2region](https://github.com/lionsoul2014/ip2region)：使用其原始地理数据和查询绑定；其授权文本随构建产物附带。
- [china-operator-ip](https://github.com/gaoyifan/china-operator-ip)：使用 china 和三大运营商列表；其 MIT 许可随产物附带。
- [MaxMind mmdbwriter](https://github.com/maxmind/mmdbwriter)：生成 MMDB。
- [maxminddb-golang](https://github.com/oschwald/maxminddb-golang) 与 [MaxMind-DB-Reader-python](https://github.com/maxmind/MaxMind-DB-Reader-python)：读取及交叉验证。

本仓库自有构建代码采用 MIT 许可。此许可不替代上游软件或数据的授权条件。
