# 07 · 验证方法

这一页说明**怎么证明修复真的生效**，以及本次在 GL-BE14000 上得到的原始数据。
完整报告（含表格、PPE 原始条目、外网下载数据）见 `verification/HWNAT-FIX-VERIFICATION.md`，
根因定案见 `verification/HWNAT-FAIL-ROOTCAUSE.md`。

## 判定标准：三个证据必须同时成立

只看吞吐是**不够的** —— 「把出问题的路径从加速里排除」也能让吞吐恢复
（见 `03-removed-dsa-bypass-workaround.md` 的教训）。必须同时看：

| # | 证据 | 修复前的样子 | 修复后的样子 |
|---|---|---|---|
| 1 | **吞吐** | 0.087~0.15 Gbit/s | 2.32~2.34 Gbit/s |
| 2 | **CPU 占用**（同样的吞吐下） | — | 从软件快转的 ~33% 降到 ~5% |
| 3 | **PPE 表项**（`/sys/kernel/debug/ppeN/entries`） | `BND … etype=2000 vlan=0,0`（MTK 私有 tag） | `BND … etype=0008 vlan=1024`（802.1Q 形状，ctrl 落在 vlan1） |

第 3 条是**最硬的证据**：它直接反映 PPE 写进硬件表项的出口 tag 编码。

## 复现步骤

```sh
# 0. 环境：两台可驱动的主机分别接在 YT9224 的两个口上
#    （本次：Ubuntu 接 sfp 10G、Windows 接 lan2 2.5G）

# 1. 确认 natflow 在作者默认配置
uci show natflow | grep -E 'ifname_group|hwnat'
#    ifname_group_type='0'，无 ifname_group 列表，hwnat='1'

# 2. 打流 + 采 CPU + 采 PPE
iperf3 -s -p 5201 &                                  # 服务端
# 客户端: iperf3 -c <server> -p 5201 -P 8 -t 20
# 同时（在路由器上）:
while :; do grep '^cpu ' /proc/stat; \
            for p in 0 1 2; do f=/sys/kernel/debug/ppe$p/entries; \
              [ -e $f ] && echo "ppe$p BND=$(grep -c BND $f)"; done; \
            grep -h 'BND' /sys/kernel/debug/ppe[012]/entries | grep <测试机IP>; \
            sleep 2; done

# 3. 对照：把 hwnat 关掉再看一遍
uci set natflow.main.hwnat=0 && uci commit natflow && /etc/init.d/natflow-boot start
# 期望：吞吐基本不变，CPU 明显升高、ppe 里没有对应 BND 表项
```

CPU 占用算法：读 `/proc/stat` 的 `cpu` 行，取 total 与 idle 的增量比
（本机 HZ=100、4 核 → 每秒总增量 400 jiffies）。

## 本次实测数据（GL-BE14000，revision `r0+36480-d1b67bef904`）

| 配置 | 正向 Win→Ubuntu | 反向 Ubuntu→Win | CPU 忙 |
|---|---|---|---|
| 修复前 `hwnat=1` | **0.087~0.15 Gbit/s** | — | — |
| 修复后 `hwnat=1` | **2.32 / 2.34 / 2.34 Gbit/s** | 1.95 / 1.94 Gbit/s | **~5%** |
| 修复后 `hwnat=0`（对照） | 2.30 / 2.34 Gbit/s | 1.93 / 1.93 Gbit/s | ~33% |

2.34 Gbit/s = 测试客户端 2.5G 口的线速上限。
反向 1.94~1.95 Gbit/s 与软件路径一致 → 属客户端接收侧的既有限制，非本次改动引入。

PPE 表项（修复后）：

```
BND orig=192.168.15.129:61622->192.168.15.157:5201  eth=1c:86:0b:3d:7f:3a->98:03:9b:a1:69:73
                                                     etype=0008  vlan=32
BND orig=192.168.15.157:5201->192.168.15.129:61622  eth=98:03:9b:a1:69:73->1c:86:0b:3d:7f:3a
                                                     etype=0008  vlan=1024
```

`vlan=32` = `yt922x_4b_port_tag(0)`（sfp）、`vlan=1024` = `yt922x_4b_port_tag(5)`（lan2）。

外网下载（WAN→LAN，出口 sfp）：`hwnat=1` 下 33.6 / 33.8 / 30.3 MB/s，
另一次实测 37.6 / **53.5 MB/s（428 Mbit/s）**，稳定不归零，CPU ~5.1%。
回流方向表项 `BND 120.46.63.139:443->192.168.15.157:49248 … etype=0008 vlan=32` 出口 tag 正确。

`dmesg` 无 natflow / DSA / PPE 报错，无 `-EOPNOTSUPP` 回落记录
（`-EOPNOTSUPP` 只会在端口号 > 8 这种异常拓扑下触发）。

## 未覆盖

见 `04-known-gaps.md`。要点：lan5~lan8（MT7530 / `mtk` tag）跨芯片未实测
（该分支代码一行未改）、>2.5 Gbit/s 未测、IPv6 路径未单独压测。
