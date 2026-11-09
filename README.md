# json-dot

零依赖 Python CLI：把嵌套 JSON 和点路径扁平键互相转换。`flatten` 把 `{"a":{"b":1}}` 变成 `{"a.b":1}`，`unflatten` 再还原回去。数组下标写成数字段，例如 `items.0.name`。

## 做什么

配置、日志字段、表格导出时常需要「嵌套结构 ↔ 扁平键」。`json-dot` 只做这一件事：

| 子命令 | 方向 | 例子 |
|--------|------|------|
| **flatten** | 嵌套 → 扁平 | `{"a":{"b":1}}` → `{"a.b":1}` |
| **unflatten** | 扁平 → 嵌套 | `{"items.0.name":"Oak Desk"}` → `{"items":[{"name":"Oak Desk"}]}` |

从文件或 stdin 读入，结果以 JSON 打印到 stdout。不连网、无第三方依赖。

## 要求

- Python 3.8+
- 标准库 only（`json` / `argparse` / `sys`）

## 用法

```bash
# 嵌套对象 + 数组 → 点路径
python3 json_dot.py flatten demo.json

# 从 stdin 读
python3 json_dot.py flatten < demo.json
cat demo.json | python3 json_dot.py flatten

# 还原
python3 json_dot.py flatten demo.json | python3 json_dot.py unflatten

# 自定义分隔符（默认是 .）
python3 json_dot.py flatten demo.json --sep /
python3 json_dot.py unflatten --sep / flat.json
```

仓库自带虚构样例 `demo.json`（一家演示商店，无真实个人信息）。

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功，stdout 为转换后的 JSON |
| 2 | 用法错误、文件不存在、坏 JSON、键冲突、非法路径或其他输入错误（详情在 stderr） |

## 规则

- 对象按键名拼接路径；数组按下标拼接，如 `items.0.name`
- 只有规范非负整数（`0`、`1`、`12`）当成数组下标；`00`、`01`、`-1` 当成普通对象键
- 空对象 / 空数组作为叶子保留：`{"a":{}}` → `{"a":{}}`，`{"a":[]}` → `{"a":[]}`
- 稀疏数组会补 `null`：`{"a.2":"x"}` → `{"a":[null,null,"x"]}`
- `flatten` 时若某个键本身包含分隔符，会报错退出（否则 `unflatten` 无法无损还原）。换一个 `--sep` 即可
- 顶层必须是对象或数组；顶层空数组 `[]` 会扁平化成 `{}`，无法从空对象分辨，见下方限制
- 数组下标超过 10000 会拒绝，避免误输入撑爆内存
- 输出为 UTF-8、缩进 2 空格、键名排序

## 示例

`demo.json` 扁平化后（节选）：

```json
{
  "items.0.id": 1,
  "items.0.name": "Oak Desk",
  "items.0.price": 199.5,
  "items.1.id": 2,
  "items.1.name": "Pine Shelf",
  "items.1.tags.0": "wood",
  "items.1.tags.1": "home",
  "meta.note": null,
  "meta.version": 1,
  "store.name": "Northwind Demo Shop",
  "store.open": true
}
```

冲突输入会非零退出，例如 `{"a":1,"a.b":2}`（`a` 既是叶子又是对象）或 `{"a.0":1,"a.x":2}`（`a` 既是数组又是对象）。

## 限制与后续

- 不转义键名里的分隔符；键包含分隔符时请换 `--sep`，或先改键名
- 顶层空数组与空对象扁平化后都是 `{}`，无法区分
- 不保留对象键的原始顺序（输出会排序）
- JSON 数字按标准库解析，大整数精度受 Python / JSON 本身限制
- 后续可考虑：键名转义、保留顺序、`--compact` 单行输出、与 jq 风格路径对齐

## License

MIT
