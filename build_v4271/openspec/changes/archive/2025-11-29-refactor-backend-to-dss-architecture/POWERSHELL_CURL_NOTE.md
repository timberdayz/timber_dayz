# PowerShell curl 问题说明

## 问题现象

在PowerShell中执行`curl`命令时，会出现提示：
```
位于命令管道位置 1 的 cmdlet Invoke-WebRequest
请为以下参数提供值:
Uri:
```

## 原因

**PowerShell的`curl`是`Invoke-WebRequest`的别名**，不是真正的curl命令。

- PowerShell 5.1+: `curl` → `Invoke-WebRequest`
- PowerShell 7+: `curl` → `Invoke-WebRequest`（但也可以使用真正的curl.exe）

## 解决方案

### 方案1: 使用Invoke-WebRequest（推荐）

```powershell
# PowerShell方式
Invoke-WebRequest -Uri http://localhost:8001/health -UseBasicParsing | Select-Object -ExpandProperty Content
```

### 方案2: 使用curl.exe（如果已安装）

```powershell
# 使用完整路径
curl.exe http://localhost:8001/health
```

### 方案3: 使用Python requests（推荐用于测试）

```powershell
python -c "import requests; print(requests.get('http://localhost:8001/health').json())"
```

### 方案4: 使用浏览器直接访问

直接访问：http://localhost:8001/health

---

**建议**: 在PowerShell中测试HTTP服务时，使用Python requests或直接浏览器访问，避免curl别名问题。

