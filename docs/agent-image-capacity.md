# Agent 镜像容量记录

统计时间：2026-11-11。范围为项目已接入的三套 Agent 数据集（Pro V1 已移除）；镜像选择 `linux/amd64`，Terminal-Bench 固定官方 4.0.0，不因查阅最新文档自动升级。

| 数据集 | 任务数 | 不重复镜像引用数 | 镜像压缩大小逐项相加 |
| --- | ---: | ---: | ---: |
| SWE-bench Mini | 50 | 50 | 52.55 GiB |
| SWE-bench Pro V2 | 642 | 642 | 979.03 GiB |
| Terminal-Bench 4.0 | 66 | 159 | 91.06 GiB |
| 合计 | — | 851 | 1,122.64 GiB（约 1.10 TiB） |

Pro V2 的 hard 51 是 642 题的子集，不另加镜像。Terminal-Bench 包括任务环境、独立 verifier 和 Compose 辅助服务；任务数不能用作镜像数量。以上不含 Skopeo 工具镜像、Agent CLI、运行时和构建中另外下载的依赖。

容量来自注册表 manifest 的压缩层大小或 Docker Hub 对应架构的 image size。Terminal-Bench 中带 digest 的镜像引用已与 Docker Hub 返回的 digest 核对。所有 851 个引用均查到大小，但统计元数据不等于镜像已下载完成。

1.10 TiB 是逐镜像相加的保守容量口径，共享层被重复计算。Pro V2 已取得全部 layer digest，单独去重后的压缩层为 506.75 GiB；其余两套通过 Docker Hub 查询了镜像大小，尚未完整取得每层清单，因此不宣称全套去重后的精确空间。仅扣除已知 Pro V2 共享层后，上述压缩容量上界可降至650.36 GiB（约 0.64 TiB）；其余共享层还会进一步节省空间。

若按不依赖共享层节省的方式规划，建议为 OCI 离线缓存预留至少 1.3 TiB；Docker 导入后的解压层、可写容器层与评测输出另留空间。不能用压缩体积推导解压体积。服务器本次检查 `/data1` 约余 1.6 TiB，可覆盖 OCI 压缩缓存的保守口径，但不足以据此保证另存全量 Docker 解压镜像与并发容器时也有足够空间。

服务器审计文件位于 `data/evalscope_dataset_manifests/`：

- `image-inventory-20261111.json`：完整镜像引用、数据集归属及 Pro V2 的层清单。
- `image-hub-sizes-20261111.json`：Docker Hub 查询结果，包含压缩大小和 digest。
- `image-capacity-summary-20261111.json`：逐数据集数量、已解析数量和容量。

本次修复了 GHCR 镜像被错误加上 Docker Hub 代理前缀，以及 Terminal-Bench Compose 辅助镜像未改写的问题。Pro V1 已从项目数据集目录和任务入口退役，旧文件在项目内归档，可避免被自动识别后重新加入。

Mini 下载仍遭遇公共源限制：毫秒镜像返回 429，DaoCloud 对该实例镜像拒绝白名单，服务器直连 Docker Hub 超时/拒绝连接。路径修复不消除上游访问限制；保留已校验的 OCI blobs 和失败状态，恢复下载时复用缓存。

依据：[EvalScope SWE-bench Pro](https://evalscope.readthedocs.io/zh-cn/latest/third_party/swe_bench_pro.html)、[EvalScope Terminal-Bench](https://evalscope.readthedocs.io/en/latest/third_party/terminal_bench.html)、[毫秒镜像源站域名映射](https://1ms.run/guide)。
