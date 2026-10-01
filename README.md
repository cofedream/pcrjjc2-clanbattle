# 基于pcrjjc2的会战推送插件

**本项目基于AGPL v3协议开源**

现在应该能根据时间正确判断出刀类型了(把boss打残了就能看到后面的色图了，这算不算某种程度的脱衣<--自己在310张卡面里面塞了35张脱衣卡面，抽卡色图什么的弱爆了
## 配置方法

1. 打开hoshino插件文件夹
2. git clone https://github.com/eggggi/pcrjjc2-clanbattle.git
3. config文件里面添加pcrjjc2-clanbattle
4. 发送 自动报刀帮助 查看可用命令的帮助
5. 发送 更新boss数据 更新当期会战boss头像血量等
6. 发送会战状态可以查看当前会战状态
7. 会战期间输入 切换会战推送 来打开/关闭推送，默认关闭
8. 关于查档线功能，结算时不能获取数据，官方结算完和会战开启时可以使用，通过获取游戏内数据，输入 查档线 可以查看各档档线，输入 查档线 1,2,3,4 可以查看 1,2,3,4 名详情，其他名次也是这样
9. 查档线新增一种按名字查询的方法， 查档线 行会名，会列出部分符合条件的行会
10. 输入 sl + ID：标记SL


### 改动说明
1. 把pcrjjc账号登录改成了怡宝的清日常账号管理模块，并附有魔改
2. 支持多群绑定同时报刀
3. 啊我好菜懒得打字了，看代码吧 \_(:з)∠)_


### 会战状态一图流的背景图

一图流默认是**纯浅色底**（这是统计报表，有底图的话照片的亮部/细节会透过半透明面板干扰读字）。
开关在 `auto_clanbattle.py` 顶部：

```python
STATUS_BG_MODE = 'solid'        # 改成 'random' 就换回随机卡面 / 自定义背景图
STATUS_BG_COLOR = '#FFE4C4'     # 纯色底的底色，暖白，和「出刀时段统计」用同一色
```

`STATUS_BG_MODE = 'random'` 时的取图顺序（每步失败都会自动往下退，不会像以前那样直接报错）：

1. `Chara.card` —— **只有作者魔改过的 hoshino 才有**。原版 `hoshino/modules/priconne/chara.py` 的 `Chara`
   只有 `name` / `is_npc` / `get_icon()`，没有 `card`，所以直接写 `c.card.open()` 会报
   `'Chara' object has no attribute 'card'`（插件以前崩掉的就是这里）
2. hoshino 资源包里的卡面：`priconne/unit/card_{角色id}_{星级}.{png,webp}`
3. 仓库里 `img/bg/` 目录的图（随机一张，右下角不画角色名水印）
4. 都没有 → 还是回到纯浅色底

#### 卡面素材从哪来

PCR 素材镜像站 <https://redive.estertion.win>，hoshino 自带的角色头像下载用的也是它
（`chara.py` 里的 `download_chara_icon()` 走的就是 `icon/unit/{id}{star}1.webp`）：

| 内容 | URL | 规格 |
| --- | --- | --- |
| 全卡面 | `https://redive.estertion.win/card/full/{id}{star}1.webp` | 1408x792（正好 16:9），约 1MB |
| 方形头像 | `https://redive.estertion.win/icon/unit/{id}{star}1.webp` | 约 20KB |

- `{id}` 是 4 位角色 id（见 `_pcr_data.py` 的 `CHARA_NAME`），`{star}` 只有 **3 和 6**，填 `1` 会返回 404
- 例：1001（凯露）3 星卡面 = `.../card/full/100131.webp`，6 星 = `.../card/full/100161.webp`
- 卡面本身是 16:9，和输出尺寸 1920x1080 一致，拉伸不会变形
- webp 不用转码，Pillow 直接能读，**下载下来按命名丢进资源目录就能被第 2 步命中**：

```bash
# 资源目录 = hoshino.config.RES_DIR（默认 ./res），注意 hoshino 的 R.img() 会自动加一层 img/
RES=./res/img/priconne/unit
mkdir -p "$RES"

# 把 1001 的 3 星卡面存成 card_1001_3.webp
curl -s -o "$RES/card_1001_3.webp" https://redive.estertion.win/card/full/100131.webp
```

想批量灌的话，按 `CHARA_NAME` 里的角色 id 循环拉 3 星/6 星即可，注意全量 200MB+ 起步。
原作者也是这个路子（他自备了 310 张卡面，并给自己的 hoshino 的 `Chara` 加了 `card` 属性）。


### 更新日志：
26.10.1 - 修复会战状态一图流背景取图报错（原版 hoshino 无 `Chara.card`）；默认改用纯浅色底；出完刀的名字颜色改为浅底可见的深金色；卡面素材来源写进代码注释和本文档 <br>
25.1.13 - 大更新，优化大部分代码和图片排版 <br>
8.02 - 大更新，支持多群同时报刀，优化大部分代码 <br>
6.26 - 支持多号切换 <br>
6.19 - 将留言板加入会战状态，在初始化会战推送时会获取一次BOSS的头像(终于不是五个猫猫头了) <br>
6.17 - 新增清空留言板；优化会战币获取，减少弹出次数；使用累计进入实战人数模式时，当boss被击杀后会重置进入实战人数。 <br>
6.8 - 修改了会战状态周目中的颜色，增加出刀时段统计，新增留言板，重启后重置留言板。

最终看起来应该是这样子的
![](example/1.jpg)

![](example/2.jpg)

查档线
![](example/3.png)
