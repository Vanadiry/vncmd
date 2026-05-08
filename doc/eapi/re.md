# 下架歌曲 API 逆向

## 背景

公开 API 对已下架歌曲无效：

- `/api/song/enhance/player/url` → code=405
- `/api/song/enhance/download/url` → code=-110

桌面客户端可正常下载，经抓包确认走的是 `/eapi/` 加密端点。

## 端点

```text
POST https://interface.music.163.com/eapi/song/enhance/download/url/v1?_nmclfl=1
Content-Type: application/x-www-form-urlencoded
Body: params={AES加密后的hex}
```

## 加密方案

- 算法：AES-128-ECB
- 密钥：`/`（16位数字+小写字母组合，不知道是否都一样就不放出来了）
- 填充：PKCS7

**明文格式**：`{路径}-{10位hex}-{JSON}-{6位hex}`

加密后 hex 大写，作为 `params` 值发送。响应同为 AES-128-ECB 加密，解密后为 JSON。

## 请求体结构

```json
{
  "immerseType": "/",
  "header": "{客户端信息JSON字符串}",
  "os": "/",
  "id": "/",
  "deviceId": "{32位hex}",
  "level": "hires",
  "verifyId": 1,
  "e_r": true
}
```

`header` 内层：

```json
{
  "clientSign": "{MAC}@@@{签名}@@@@@@{UUID}{签名}",
  "os": "/",
  "appver": "/",
  "deviceId": "{设备UUID}",
  "requestId": 0,
  "osver": "/"
}
```

## 响应示例

```json
{
  "data": {
    "id": /,
    "url": "http://m801.music.126.net/.../xxx.mp3?...",
    "br": 320000,
    "size": 10573366,
    "code": 200,
    "type": "mp3",
    "level": "exhigh"
  },
  "code": 200
}
```

## 结论

`clientSign` 格式为 `{MAC}@@@{签名}@@@@@@{UUID}{签名}`，由客户端本地生成，服务端校验且有时效性。重放抓包获取的 `clientSign` 在数分钟后即返回空响应。

脱离官方客户端无法生成有效的 `clientSign`，因此该端点不可作为通用下载方案。
