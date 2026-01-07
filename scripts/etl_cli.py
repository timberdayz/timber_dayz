#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL命令行工具

提供便捷的命令行接口来执行ETL操作：
- scan: 扫描文件并注册到catalog
- ingest: 执行入库
- status: 查看catalog状态
- retry: 重试失败的文件
"""

import click
import sys
from pathlib import Path
from datetime import datetime, timedelta


@click.group()
def cli():
    """🚀 跨境电商ERP系统 - ETL命令行工具"""
    pass


@cli.command()
@click.argument('directories', nargs=-1, type=click.Path(exists=True))
@click.option('--source', default='temp/outputs', help='来源标识')
def scan(directories, source):
    """
    📂 扫描目录并注册文件到catalog
    
    示例:
        python scripts/etl_cli.py scan temp/outputs
        python scripts/etl_cli.py scan temp/outputs data/input/manual_uploads
    """
    from modules.services.catalog_scanner import scan_and_register
    
    paths = [Path(d) for d in directories] if directories else [Path('temp/outputs')]
    
    click.echo("=" * 70)
    click.echo("📂 文件扫描与注册")
    click.echo("=" * 70)
    click.echo(f"扫描目录: {', '.join(str(p) for p in paths)}")
    click.echo()
    
    try:
        with click.progressbar(length=100, label='扫描中') as bar:
            result = scan_and_register(paths)
            bar.update(100)
        
        click.echo()
        click.echo("✅ 扫描完成!")
        click.echo(f"   总计: {result.seen}")
        click.echo(f"   新增: {result.registered}")
        click.echo(f"   已存在: {result.skipped}")
        
        if result.registered > 0:
            click.echo()
            click.secho(f"💡 提示: {result.registered}个新文件已注册，可以执行入库操作", fg='green')
            click.echo(f"   运行: python scripts/etl_cli.py ingest")
    
    except Exception as e:
        click.secho(f"❌ 扫描失败: {str(e)}", fg='red', err=True)
        sys.exit(1)


@cli.command()
@click.option('--limit', default=50, help='每批处理文件数', show_default=True)
@click.option('--domain', multiple=True, help='数据域（可多个），如：products, orders, traffic')
@click.option('--recent-hours', type=int, help='只处理最近N小时的文件')
@click.option('--verbose', '-v', is_flag=True, help='显示详细进度')
def ingest(limit, domain, recent_hours, verbose):
    """
    📥 执行入库（从catalog_files读取pending状态）
    
    示例:
        python scripts/etl_cli.py ingest
        python scripts/etl_cli.py ingest --limit 100 --domain products --domain orders
        python scripts/etl_cli.py ingest --recent-hours 24 -v
    """
    from modules.services.ingestion_worker import run_once
    
    domains = list(domain) if domain else None
    
    click.echo("=" * 70)
    click.echo("📥 数据入库")
    click.echo("=" * 70)
    click.echo(f"批次大小: {limit}")
    click.echo(f"数据域: {domains or '全部'}")
    if recent_hours:
        click.echo(f"时间范围: 最近{recent_hours}小时")
    click.echo()
    
    current_file = None
    
    def progress_callback(cf, stage, msg):
        nonlocal current_file
        if stage == 'start':
            current_file = cf.file_name
            if verbose:
                click.echo(f"  处理: {cf.file_name[:60]}")
        elif stage == 'done':
            if verbose:
                click.secho(f"    ✅ {msg}", fg='green')
        elif stage == 'failed':
            click.secho(f"    ❌ {cf.file_name[:50]} - {msg}", fg='red')
        elif stage == 'phase' and verbose:
            # 内部阶段进度
            click.echo(f"    ~ {msg}")
    
    try:
        click.echo("正在处理...")
        
        stats = run_once(
            limit=limit,
            domains=domains,
            recent_hours=recent_hours,
            progress_cb=progress_callback if verbose else None
        )
        
        click.echo()
        click.echo("✅ 入库完成!")
        click.echo(f"   待处理: {stats.picked}")
        click.echo(f"   成功: {stats.succeeded}")
        click.echo(f"   失败: {stats.failed}")
        
        if stats.failed > 0:
            click.echo()
            click.secho("⚠️  提示: 失败的数据已隔离到data_quarantine表", fg='yellow')
            click.echo("   查询: python scripts/etl_cli.py status --quarantine")
    
    except Exception as e:
        click.secho(f"❌ 入库失败: {str(e)}", fg='red', err=True)
        import traceback
        if verbose:
            click.echo(traceback.format_exc(), err=True)
        sys.exit(1)


@cli.command()
@click.option('--quarantine', is_flag=True, help='显示隔离数据统计')
@click.option('--detail', is_flag=True, help='显示详细信息')
def status(quarantine, detail):
    """
    📊 查看catalog状态统计
    
    示例:
        python scripts/etl_cli.py status
        python scripts/etl_cli.py status --quarantine
        python scripts/etl_cli.py status --detail
    """
    import os
    from sqlalchemy import create_engine, text
    from modules.core.secrets_manager import get_secrets_manager
    
    # 获取数据库连接
    url = os.getenv('DATABASE_URL')
    if not url:
        sm = get_secrets_manager()
        url = f"sqlite:///{sm.get_unified_database_path()}"
    
    engine = create_engine(url)
    
    click.echo("=" * 70)
    click.echo("📊 Catalog状态统计")
    click.echo("=" * 70)
    click.echo()
    
    try:
        with engine.connect() as conn:
            # 总文件数
            total = conn.execute(text("SELECT COUNT(*) FROM catalog_files")).scalar()
            click.echo(f"📁 总文件数: {total}")
            click.echo()
            
            # 按状态统计
            click.echo("📋 按状态分布:")
            status_query = text("""
                SELECT status, COUNT(*) as count
                FROM catalog_files
                GROUP BY status
                ORDER BY count DESC
            """)
            status_stats = conn.execute(status_query).fetchall()
            
            for status, count in status_stats:
                icon = {
                    'pending': '⏳',
                    'ingested': '✅',
                    'failed': '❌',
                }.get(status, '📄')
                percentage = (count / total * 100) if total > 0 else 0
                click.echo(f"   {icon} {status:12s}: {count:5d} ({percentage:5.1f}%)")
            
            click.echo()
            
            # 按数据域统计
            click.echo("📊 按数据域分布:")
            domain_query = text("""
                SELECT COALESCE(data_domain, 'unknown') as domain, COUNT(*) as count
                FROM catalog_files
                GROUP BY data_domain
                ORDER BY count DESC
            """)
            domain_stats = conn.execute(domain_query).fetchall()
            
            for domain, count in domain_stats:
                percentage = (count / total * 100) if total > 0 else 0
                click.echo(f"   {domain:15s}: {count:5d} ({percentage:5.1f}%)")
            
            # 详细信息
            if detail:
                click.echo()
                click.echo("📈 最近处理的文件（最多10个）:")
                recent_query = text("""
                    SELECT 
                        file_name,
                        status,
                        datetime(processed_at) as processed_at
                    FROM catalog_files
                    WHERE processed_at IS NOT NULL
                    ORDER BY processed_at DESC
                    LIMIT 10
                """)
                recent_files = conn.execute(recent_query).fetchall()
                
                for file_name, status, processed_at in recent_files:
                    icon = '✅' if status == 'ingested' else '❌'
                    click.echo(f"   {icon} {file_name[:50]}")
                    click.echo(f"      {processed_at}")
            
            # 隔离数据统计
            if quarantine:
                click.echo()
                click.echo("🔍 隔离数据统计:")
                quarantine_query = text("""
                    SELECT 
                        error_type,
                        COUNT(*) as count
                    FROM data_quarantine
                    GROUP BY error_type
                    ORDER BY count DESC
                    LIMIT 10
                """)
                quarantine_stats = conn.execute(quarantine_query).fetchall()
                
                if quarantine_stats:
                    for error_type, count in quarantine_stats:
                        click.echo(f"   ❌ {error_type:30s}: {count:5d}")
                    
                    total_quarantine = sum(c for _, c in quarantine_stats)
                    click.echo()
                    click.echo(f"   总计隔离记录: {total_quarantine}")
                else:
                    click.echo("   ✅ 无隔离数据")
    
    except Exception as e:
        click.secho(f"❌ 查询失败: {str(e)}", fg='red', err=True)
        sys.exit(1)


@cli.command()
@click.option('--pattern', help='文件名匹配模式（SQL LIKE语法）')
@click.option('--domain', help='数据域')
@click.option('--all', 'retry_all', is_flag=True, help='重试所有失败的文件')
@click.option('--dry-run', is_flag=True, help='仅显示将要重试的文件，不实际修改')
def retry(pattern, domain, retry_all, dry_run):
    """
    🔄 重试失败的文件
    
    示例:
        python scripts/etl_cli.py retry --pattern "%shopee%"
        python scripts/etl_cli.py retry --domain products
        python scripts/etl_cli.py retry --all --dry-run
    """
    import os
    from sqlalchemy import create_engine, text
    from modules.core.secrets_manager import get_secrets_manager
    
    # 获取数据库连接
    url = os.getenv('DATABASE_URL')
    if not url:
        sm = get_secrets_manager()
        url = f"sqlite:///{sm.get_unified_database_path()}"
    
    engine = create_engine(url)
    
    click.echo("=" * 70)
    click.echo("🔄 重试失败的文件")
    click.echo("=" * 70)
    
    try:
        with engine.begin() as conn:
            # 构建查询
            where_clauses = ["status = 'failed'"]
            params = {}
            
            if pattern:
                where_clauses.append("file_name LIKE :pattern")
                params['pattern'] = pattern
            
            if domain:
                where_clauses.append("data_domain = :domain")
                params['domain'] = domain
            
            where_sql = " AND ".join(where_clauses)
            
            # 查询失败的文件
            select_query = text(f"""
                SELECT id, file_name, error_message
                FROM catalog_files
                WHERE {where_sql}
                ORDER BY id
            """)
            
            failed_files = conn.execute(select_query, params).fetchall()
            
            if not failed_files:
                click.echo("✅ 没有符合条件的失败文件")
                return
            
            click.echo(f"找到 {len(failed_files)} 个失败的文件:")
            click.echo()
            
            for file_id, file_name, error_msg in failed_files[:10]:  # 最多显示10个
                click.echo(f"   ❌ {file_name[:60]}")
                if error_msg:
                    click.echo(f"      错误: {error_msg[:80]}")
            
            if len(failed_files) > 10:
                click.echo(f"   ... 还有 {len(failed_files) - 10} 个文件")
            
            click.echo()
            
            if dry_run:
                click.secho("💡 这是dry-run模式，没有实际修改数据", fg='yellow')
                return
            
            if not retry_all and not click.confirm("确认重试这些文件？"):
                click.echo("取消操作")
                return
            
            # 更新状态为pending
            update_query = text(f"""
                UPDATE catalog_files
                SET status = 'pending', 
                    error_message = NULL
                WHERE {where_sql}
            """)
            
            result = conn.execute(update_query, params)
            
            click.echo()
            click.secho(f"✅ 已重置 {result.rowcount} 个文件为pending状态", fg='green')
            click.echo()
            click.echo("💡 提示: 现在可以执行入库操作")
            click.echo("   运行: python scripts/etl_cli.py ingest")
    
    except Exception as e:
        click.secho(f"❌ 操作失败: {str(e)}", fg='red', err=True)
        sys.exit(1)


@cli.command()
@click.argument('source_dir', type=click.Path(exists=True))
@click.option('--limit', default=100, help='最多处理文件数', show_default=True)
@click.option('--domain', multiple=True, help='限制数据域')
@click.option('--verbose', '-v', is_flag=True, help='显示详细输出')
def run(source_dir, limit, domain, verbose):
    """
    🚀 完整ETL流程（扫描 + 入库）
    
    这是一个便捷命令，等同于先运行scan再运行ingest。
    
    示例:
        python scripts/etl_cli.py run temp/outputs
        python scripts/etl_cli.py run temp/outputs --limit 50 -v
    """
    from modules.services.catalog_scanner import scan_and_register
    from modules.services.ingestion_worker import run_once
    
    source_path = Path(source_dir)
    domains = list(domain) if domain else None
    
    click.echo("=" * 70)
    click.echo("🚀 完整ETL流程")
    click.echo("=" * 70)
    click.echo(f"源目录: {source_path}")
    click.echo(f"限制: {limit}个文件")
    click.echo(f"数据域: {domains or '全部'}")
    click.echo()
    
    try:
        # 步骤1：扫描
        click.echo("📂 步骤1/2: 扫描文件...")
        scan_result = scan_and_register([source_path])
        click.echo(f"   发现: {scan_result.seen}, 新增: {scan_result.registered}, 跳过: {scan_result.skipped}")
        
        if scan_result.registered == 0 and scan_result.seen == 0:
            click.secho("✅ 没有文件需要处理", fg='green')
            return
        
        click.echo()
        
        # 步骤2：入库
        click.echo("📥 步骤2/2: 数据入库...")
        
        def progress(cf, stage, msg):
            if stage == 'start' and verbose:
                click.echo(f"  处理: {cf.file_name[:60]}")
            elif stage == 'done' and verbose:
                click.secho(f"    ✅ {msg}", fg='green')
            elif stage == 'failed':
                click.secho(f"    ❌ {cf.file_name[:50]} - {msg}", fg='red')
        
        stats = run_once(
            limit=limit,
            domains=domains,
            progress_cb=progress
        )
        
        click.echo()
        click.echo("=" * 70)
        click.echo("📊 ETL结果汇总")
        click.echo("=" * 70)
        click.echo(f"待处理: {stats.picked}")
        click.echo(f"成功: {stats.succeeded}")
        click.echo(f"失败: {stats.failed}")
        
        if stats.failed > 0:
            click.echo()
            click.secho("⚠️  提示: 失败的数据已隔离到data_quarantine表", fg='yellow')
        
        click.echo()
        click.secho("✅ ETL流程完成！", fg='green')
    
    except Exception as e:
        click.secho(f"❌ ETL失败: {str(e)}", fg='red', err=True)
        import traceback
        if verbose:
            click.echo(traceback.format_exc(), err=True)
        sys.exit(1)


@cli.command()
@click.option('--days', default=30, type=int, help='删除N天前已入库的记录', show_default=True)
@click.option('--dry-run', is_flag=True, help='仅显示将要删除的记录数，不实际删除')
def cleanup(days, dry_run):
    """
    🧹 清理旧的catalog记录
    
    删除指定天数之前已成功入库的catalog记录，减小表大小。
    
    示例:
        python scripts/etl_cli.py cleanup --days 30 --dry-run
        python scripts/etl_cli.py cleanup --days 60
    """
    import os
    from sqlalchemy import create_engine, text
    from modules.core.secrets_manager import get_secrets_manager
    
    url = os.getenv('DATABASE_URL')
    if not url:
        sm = get_secrets_manager()
        url = f"sqlite:///{sm.get_unified_database_path()}"
    
    engine = create_engine(url)
    
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    
    click.echo("=" * 70)
    click.echo("🧹 清理旧的catalog记录")
    click.echo("=" * 70)
    click.echo(f"删除 {days} 天前的已入库记录（{cutoff_date}之前）")
    click.echo()
    
    try:
        with engine.begin() as conn:
            # 查询将要删除的记录数
            count_query = text("""
                SELECT COUNT(*) 
                FROM catalog_files
                WHERE status = 'ingested'
                AND processed_at < :cutoff_date
            """)
            
            count = conn.execute(count_query, {'cutoff_date': cutoff_date}).scalar()
            
            if count == 0:
                click.echo("✅ 没有需要清理的记录")
                return
            
            click.echo(f"将要删除 {count} 条记录")
            click.echo()
            
            if dry_run:
                click.secho("💡 这是dry-run模式，没有实际删除数据", fg='yellow')
                return
            
            if not click.confirm("确认删除？"):
                click.echo("取消操作")
                return
            
            # 执行删除
            delete_query = text("""
                DELETE FROM catalog_files
                WHERE status = 'ingested'
                AND processed_at < :cutoff_date
            """)
            
            result = conn.execute(delete_query, {'cutoff_date': cutoff_date})
            
            click.echo()
            click.secho(f"✅ 已删除 {result.rowcount} 条记录", fg='green')
    
    except Exception as e:
        click.secho(f"❌ 清理失败: {str(e)}", fg='red', err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()

