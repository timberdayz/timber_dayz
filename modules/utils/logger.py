"""日志转发层(兼容)

背景
----
19 个模块从 ``modules.utils.logger`` 取日志对象, 但这个模块**从未存在过**::

    git log --all -- modules/utils/logger.py     # 空

—— 是路径写错了, 真正的实现在 :mod:`modules.core.logger`。

后果不是「日志不输出」, 而是**这些模块根本无法被导入**。实测
``modules.services.shopee_playwright_exporter`` /
``modules.services.recipe_executor`` /
``modules.utils.platform_adapters`` /
``modules.utils.recording_registry`` 全部在 import 阶段抛
``ModuleNotFoundError`` —— 任何触达它们的调用方都会直接崩。

本模块是**薄转发层**, 把三个符号转发到 :mod:`modules.core.logger`:

* ``get_logger(name, level="INFO")`` —— 逐字转发
* ``logger`` —— 模块级 logger 实例(等价于 ``get_logger(__name__)``)
* ``Logger`` —— ``get_logger`` 的别名(历史调用点写作 ``Logger(__name__)``)

为什么是「加一层」而不是逐个改 19 个文件
----------------------------------------
逐个改 import 当然可行, 但这 19 处都在 legacy 采集块内, 而本次改动的目标是
**解地雷**(消除必然失败的导入), 不是重整 legacy 代码。

* 1 个转发文件 + 0 处调用方改动 -> 一次性消除 20 处 ImportError 地雷
* 改动面最小, 可整体回退
* 调用方想彻底迁移时, 把这 19 处 import 换到 :mod:`modules.core.logger` 即可,
  本转发层随时可以删掉

保留兼容层而不是直接删引用, 是因为这些模块**本身在被维护**(例如
``shopee_playwright_exporter.py`` 最近还在改), 它们的日志需求是真实存在的 ——
缺的只是一个能 import 的路径。
"""

from __future__ import annotations

from modules.core.logger import get_logger as get_logger

__all__ = ["get_logger", "logger", "Logger"]

#: 模块级 logger —— 对齐 ``from modules.core.logger import get_logger`` 的用法
logger = get_logger(__name__)

#: 历史别名 —— 调用点写作 ``Logger(__name__)``, 语义就是取一个 logger
Logger = get_logger
