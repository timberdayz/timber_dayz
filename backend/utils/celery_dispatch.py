"""Celery 派发助手 —— 保证派发动作**永不阻塞 asyncio 事件循环**。

为什么需要它
------------
``task.delay()`` / ``task.apply_async()`` 表面上只是「把消息发到 broker」,
但在 Redis 不可达(宕机 / 网络分区 / 密码错)时, 这条调用会**同步阻塞**地
反复重试连接, 最长可达十几秒。

关键在于: 这个阻塞发生在**调用方所在的线程**里。如果调用方是 async 函数
(也就是 API 请求处理链路), 那么阻塞期间**整个事件循环被冻住** ——
所有并发请求一起挂起, 表现为「Redis 一抖, 整个 API 500 / 整个系统卡住」。

本模块的做法
------------
把发布动作丢进线程池(``asyncio.to_thread``): 线程被阻塞时, 事件循环照常
调度其它协程。于是:

* Redis **正常**时: 派发耗时不变(生产实测中位数 0.52 ms),
  只是多一次线程切换, 可忽略;
* Redis **不可达**时: 只有**这一个**请求在等, 其它请求照常服务,
  「全站一起挂」变成「单个请求变慢」。

用法
----
把 async 上下文里的::

    celery_task = sync_batch_task.apply_async(args=(...), kwargs={...})

改成::

    celery_task = await dispatch_task(sync_batch_task, args=(...), kwargs={...})

``delay`` 风格的调用(关键字参数)同样支持::

    await dispatch_task(extract_product_images_task, kwargs={...})

同步上下文(Celery worker 内部)里**不要**用本模块 —— 那里阻塞只会占用一个
worker 槽, 不是全站事件循环, 线程切换反而是多余的损耗。
"""

import asyncio
from typing import Any, Dict, Optional, Sequence, Tuple


def _publish(
    task: Any,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    options: Dict[str, Any],
) -> Any:
    """真正执行发布的同步函数(跑在线程池里)。"""
    return task.apply_async(args=args, kwargs=kwargs, **options)


async def dispatch_task(
    task: Any,
    args: Optional[Sequence[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    **options: Any,
) -> Any:
    """在**线程池**里发布一个 Celery 任务, 返回 ``AsyncResult``。

    参数与 ``Task.apply_async`` 对齐:

    * ``args``   —— 位置参数(元组);
    * ``kwargs`` —— 关键字参数;
    * ``**options`` —— 其余 ``apply_async`` 选项(``priority`` / ``queue`` /
      ``ignore_result`` / ``countdown`` / ``expires`` 等)。

    异常语义与直接调用 ``apply_async`` 完全一致: 发布失败照常抛出,
    由调用点原有的 ``except`` 兜底 —— 本模块**不吞异常**, 也不改变
    「派发失败就不置成功标记」这类既有语义。
    """
    return await asyncio.to_thread(
        _publish,
        task,
        tuple(args or ()),
        dict(kwargs or {}),
        dict(options),
    )


__all__ = ["dispatch_task"]
