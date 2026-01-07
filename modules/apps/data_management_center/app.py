#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据管理中心应用

提供从 run_new.py 进入的一站式后端数据管理：
- 清单扫描（catalog_scanner）
- 入库执行（ingestion_worker）
- 队列统计/失败清单/重试
- 失败文件列头预览（辅助映射与规则增强）
- 快速打开新库仪表盘（可选）

规范：
- 类级元数据 NAME/VERSION/DESCRIPTION
- 导入阶段零副作用；仅在菜单操作时执行 I/O
"""

from typing import Any, Dict, Optional
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text as T

from modules.core.base_app import BaseApplication
from modules.core.logger import get_logger
from modules.core.secrets_manager import get_secrets_manager

logger = get_logger(__name__)


class DataManagementCenterApp(BaseApplication):
    NAME = "数据管理中心"
    VERSION = "1.0.0"
    DESCRIPTION = "统一管理清单扫描、入库执行、队列诊断与快速预览"

    def __init__(self):
        super().__init__()
        self.name = self.NAME
        self.version = self.VERSION
        self.description = self.DESCRIPTION

    # 基础设施
    def _engine(self):
        url = os.getenv("DATABASE_URL") or f"sqlite:///{get_secrets_manager().get_unified_database_path()}"
        return create_engine(url, future=True)

    def _show_custom_menu(self):
        while True:
            print(f"\n📦 {self.name} - 功能菜单")
            print("-" * 40)
            print("1. 📁 扫描目录并登记 (catalog_scanner)")
            print("2. 🏭 执行一次入库 (ingestion_worker.run_once)")
            print("3. 🧾 查看入库队列统计 (pending/ingested/failed)")
            print("4. ❌ 查看失败详情 Top 20")
            print("5. 🔁 将最近 N 条失败重置为 pending (默认20)")
            print("6. 🔍 预览失败文件列头/前5行 (输入 catalog_files.id)")
            print("7. 🌐 打开新DB仪表盘（Streamlit，可选）")
            print("8. 🔄 自动循环入库（直到 pending<阈值 或 超时）")
            print("9. 📚 表统计概览（维度/事实行数）")
            print("0. 🔙 返回主菜单")

            choice = input("\n请选择操作 (0-9): ").strip()
            try:
                if choice == "0":
                    break
                elif choice == "1":
                    self._scan_catalog()
                elif choice == "2":
                    self._run_ingestion_once()
                elif choice == "3":
                    self._show_queue_stats()
                elif choice == "4":
                    self._show_failed_details()
                elif choice == "5":
                    self._reset_failed_to_pending()
                elif choice == "6":
                    self._peek_failed_columns()
                elif choice == "7":
                    self._open_new_db_dashboard()
                elif choice == "8":
                    self._run_ingestion_auto_loop()
                elif choice == "9":
                    self._show_table_overview()
                else:
                    print("❌ 无效选择，请重试")
                input("\n按回车键继续...")
            except KeyboardInterrupt:
                print("\n🔙 返回上级菜单")
                break
            except Exception as e:
                logger.error(f"菜单操作异常: {e}")
                print(f"❌ 操作失败: {e}")
                input("按回车键继续...")

    # 动作实现
    def _scan_catalog(self):
        print("\n📁 扫描目录并登记…")
        try:
            from modules.services.catalog_scanner import main as scan_main
            scan_main()
            print("✅ 扫描完成")
        except Exception as e:
            print(f"❌ 扫描失败: {e}")
    def _pending_counts(self, domains: Optional[str] = None) -> int:
        sql = "select count(*) from catalog_files where status='pending'"
        params = {}
        if domains:
            doms = [d.strip() for d in domains.split(',') if d.strip()]
            if doms:
                placeholders = ",".join([f":d{i}" for i in range(len(doms))])
                sql += f" and data_domain in ({placeholders})"
                params = {f"d{i}": dom for i, dom in enumerate(doms)}
        with self._engine().connect() as c:
            return int(c.execute(T(sql), params).scalar() or 0)

    def _run_ingestion_once(self):
        print("\n[Batch] 执行入库 (一次批处理)…")
        try:
            from modules.services.ingestion_worker import run_once
            # 步骤1：输入参数
            try:
                limit = int(input("- 步骤1/5: 每批处理条数 limit (默认50): ").strip() or "50")
            except Exception:
                limit = 50
            domains = input("- 步骤2/5: 指定数据域(可选, 逗号分隔，如 products,orders): ").strip() or None
            if domains:
                domains = ",".join([d.strip().lower() for d in domains.split(',') if d.strip()])
            recent_hours = input("- 步骤3/5: 仅处理最近 N 小时(可选，回车跳过): ").strip()
            recent_hours = int(recent_hours) if recent_hours else None
            # 步骤4：统计队列
            before = self._pending_counts(domains)
            print(f"- 步骤4/5: 当前待处理 pending={before}")
            # 步骤5：执行（逐文件进度打印）
            def _cb(cf, stage, msg):
                try:
                    print(f"  - [{cf.id}] {stage}: {cf.file_name} ({cf.platform_code or '-'} / {cf.data_domain or '-'}) {msg or ''}", flush=True)
                except Exception:
                    pass
            stats = run_once(limit=limit, domains=(domains.split(',') if domains else None), recent_hours=recent_hours, progress_cb=_cb)
            print(f"- 步骤5/5: 执行完成 picked={stats.picked}, succeeded={stats.succeeded}, failed={stats.failed}")
        except Exception as e:
            print(f"❌ 入库执行失败: {e}")




    def _show_queue_stats(self):
        print("\n🧾 入库队列统计…")
        with self._engine().connect() as c:
            rows = c.execute(T("select data_domain, status, count(*) cnt from catalog_files group by 1,2 order by 1,2"))
            data = rows.mappings().all()
            if not data:
                print("(空)")
                return
            print("data_domain | status | count")
            for r in data:
                dd = r.get('data_domain') or '-'
                st = r.get('status') or '-'
                cnt = r.get('cnt')
                print(f"{str(dd):<12} | {str(st):<8} | {cnt}")

    def _show_failed_details(self):
        print("\n❌ 失败详情 Top 20…")
        with self._engine().connect() as c:
            rows = c.execute(T("select id, file_name, platform_code, data_domain, error_message from catalog_files where status='failed' order by id desc limit 20")).mappings().all()
            if not rows:
                print("(无失败)")
                return
            for r in rows:
                print(f"#{r['id']:>4d} | {r['platform_code'] or '-':<8s} | {r['data_domain'] or '-':<9s} | {r['file_name']}")

    def _show_table_overview(self):
        print("\n📚 表统计概览…")
        with self._engine().connect() as c:
            def _count(tbl: str):
                try:
                    return int(c.execute(T(f"select count(*) from {tbl}")).scalar() or 0)
                except Exception:
                    return None
            def _minmax(tbl: str, col: str):
                try:
                    row = c.execute(T(f"select min({col}) as min_v, max({col}) as max_v from {tbl}")).mappings().first()
                    return (row.get('min_v'), row.get('max_v')) if row else (None, None)
                except Exception:
                    return (None, None)

            dpl = _count("dim_platforms")
            ds = _count("dim_shops")
            dp = _count("dim_products")
            dcr = _count("dim_currency_rates")
            fp = _count("fact_product_metrics")
            fo = _count("fact_orders")
            foi = _count("fact_order_items")
            cf = _count("catalog_files")

            md_min, md_max = _minmax("fact_product_metrics", "metric_date")
            od_min, od_max = _minmax("fact_orders", "order_date_local")

            print(f"dim_platforms: {dpl}")
            print(f"dim_shops: {ds}")
            print(f"dim_products: {dp}")
            print(f"dim_currency_rates: {dcr}")
            print(f"fact_product_metrics: {fp} (date range: {md_min} ~ {md_max})")
            print(f"fact_orders: {fo} (date range: {od_min} ~ {od_max})")
            print(f"fact_order_items: {foi}")

            try:
                rows = c.execute(T("select status, count(*) cnt from catalog_files group by status")).mappings().all()
                by_status = { (r.get('status') or '-') : r.get('cnt') for r in rows }
                print(f"catalog_files: {cf} (pending={by_status.get('pending',0)}, ingested={by_status.get('ingested',0)}, failed={by_status.get('failed',0)})")
            except Exception:
                print(f"catalog_files: {cf}")

                if r.get('error_message'):
                    print(f"   ↳ {r['error_message']}")

    def _run_ingestion_auto_loop(self):
        print("\n[Auto] 自动循环入库…")
        try:
            from time import sleep, time
            from modules.services.ingestion_worker import run_once
            # 参数输入
            try:
                limit = int(input("- 步骤1/6: limit/批 (默认50): ").strip() or "50")
            except Exception:
                limit = 50
            domains = input("- 步骤2/6: 数据域过滤(可选, 逗号分隔，如 products,orders): ").strip() or None
            if domains:
                domains = ",".join([d.strip().lower() for d in domains.split(',') if d.strip()])
            recent_hours = input("- 步骤3/6: 仅处理最近 N 小时(可选，回车跳过): ").strip()
            recent_hours = int(recent_hours) if recent_hours else None
            try:
                pending_threshold = int(input("- 步骤4/6: 停止阈值 pending< (默认5): ").strip() or "5")
            except Exception:
                pending_threshold = 5
            try:
                max_minutes = int(input("- 步骤5/6: 最长运行分钟数 (默认10): ").strip() or "10")
            except Exception:
                max_minutes = 10
            try:
                interval_sec = int(input("- 步骤6/6: 轮次间隔秒 (默认10): ").strip() or "10")
            except Exception:
                interval_sec = 10

            dom_list = (domains.split(',') if domains else None)
            start_ts = time()
            round_no = 0
            total_picked = total_succ = total_fail = 0

            while True:
                round_no += 1
                print(f"\n== 轮次 {round_no} ==")
                # 步骤1：统计队列
                pending = self._pending_counts(domains)
                print(f"- 步骤1/4: 当前 pending={pending}")
                if pending <= pending_threshold:
                    print(f"\u2705 达到停止阈值，结束 (pending={pending} <= {pending_threshold})")
                    break
                # 步骤2：执行一轮（逐文件进度打印）
                print(f"- 步骤2/4: 执行 run_once(limit={limit}, domains={domains or '-'}, recent_hours={recent_hours or '-'})")
                def _cb(cf, stage, msg):
                    try:
                        print(f"  - [{cf.id}] {stage}: {cf.file_name} ({cf.platform_code or '-'} / {cf.data_domain or '-'}) {msg or ''}", flush=True)
                    except Exception:
                        pass
                stats = run_once(limit=limit, domains=dom_list, recent_hours=recent_hours, progress_cb=_cb)
                print(f"- 步骤3/4: 本轮结果 picked={stats.picked}, succeeded={stats.succeeded}, failed={stats.failed}")
                total_picked += stats.picked
                total_succ += stats.succeeded
                total_fail += stats.failed
                # 步骤4：时间与间隔控制
                elapsed_min = (time() - start_ts) / 60.0
                print(f"- 步骤4/4: 累计 picked={total_picked}, succeeded={total_succ}, failed={total_fail}, 已运行{elapsed_min:.1f}分钟")
                if elapsed_min >= max_minutes:
                    print(f"\u26a0\ufe0f 达到最长运行时间 {max_minutes} 分钟，结束")
                    break
                sleep(max(1, interval_sec))
        except Exception as e:
            print(f"\u274c 自动循环失败: {e}")


    def _reset_failed_to_pending(self):
        try:
            n = int(input("输入要重置的条数 N (默认20): ").strip() or "20")
        except Exception:
            n = 20
        with self._engine().begin() as c:
            ids = [r[0] for r in c.execute(T("select id from catalog_files where status='failed' order by id desc limit :n"), {"n": n}).all()]
            if not ids:
                print("(无可重置的失败记录)")
                return
            c.execute(T("update catalog_files set status='pending', error_message=null where id in (%s)" % ",".join(map(str, ids))))
        print(f"✅ 已重置 {len(ids)} 条失败记录为 pending")

    def _peek_failed_columns(self):
        try:
            cid = int(input("输入 catalog_files.id: ").strip())
        except Exception:
            print("❌ 无效ID")
            return
        from modules.services.ingestion_worker import _read_dataframe2
        with self._engine().connect() as c:
            row = c.execute(T("select file_path from catalog_files where id=:i"), {"i": cid}).first()
            if not row:
                print("❌ 未找到记录")
                return
            path = Path(row[0])
        try:
            df = _read_dataframe2(path)
            cols = [str(c) for c in df.columns]
            print("COLUMNS:", cols)
            print("HEAD (5):")
            print(df.head(5).to_string(index=False))
        except Exception as e:
            print(f"❌ 读取失败: {e}")

    def _open_new_db_dashboard(self):
        try:
            import subprocess
            frontend = Path(__file__).resolve().parents[3] / "frontend_streamlit" / "pages" / "10_new_db_dashboard.py"
            if not frontend.exists():
                print("❌ 找不到前端页: frontend_streamlit/pages/10_new_db_dashboard.py")
                return
            port = os.environ.get("STREAMLIT_PORT", "8510")
            cmd = [sys.executable, "-m", "streamlit", "run", str(frontend), "--server.port", str(port), "--server.address", "0.0.0.0", "--server.headless", "true"]
            subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parents[3]))
            print(f"✅ 已启动，新DB仪表盘: http://localhost:{port}")
        except Exception as e:
            print(f"❌ 启动失败: {e}")

    # 运行入口
    def run(self) -> bool:
        try:
            self.show_menu()
            return True
        except Exception as e:
            logger.error(f"运行异常: {e}")
            return False

