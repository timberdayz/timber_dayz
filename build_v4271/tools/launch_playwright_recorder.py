"""
独立的Playwright录制启动器
在独立进程中运行，避免Windows线程兼容性问题

使用playwright codegen命令来录制操作并生成代码
"""

import sys
import argparse
import subprocess
from pathlib import Path


def launch_recorder(login_url: str, platform: str, component_type: str, output_file: str):
    """
    启动Playwright codegen来录制操作
    生成的代码会保存到输出文件
    """
    print(f"[Recorder] Starting for {platform}/{component_type}")
    print(f"[Recorder] Login URL: {login_url}")
    print(f"[Recorder] Output file: {output_file}")
    
    try:
        # 确保输出目录存在
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 构建playwright codegen命令
        cmd = [
            sys.executable, '-m', 'playwright', 'codegen',
            '--target', 'python',  # 生成Python代码
            '--output', str(output_path),  # 输出文件
            '--save-storage', str(output_path.with_suffix('.json')),  # 保存存储状态
        ]
        
        # 如果有登录URL，添加到命令
        if login_url:
            cmd.append(login_url)
        
        print(f"[Recorder] Launching Playwright codegen...")
        print(f"[Recorder] Command: {' '.join(cmd)}")
        print("[Recorder] Please perform your actions in the browser")
        print("[Recorder] When done, close the browser window to finish recording")
        
        # 运行codegen命令（阻塞直到用户关闭浏览器）
        result = subprocess.run(cmd, capture_output=False, text=True)
        
        if result.returncode == 0:
            print(f"[Recorder] Recording completed successfully")
            print(f"[Recorder] Code saved to: {output_file}")
        else:
            print(f"[Recorder] Recording failed with code: {result.returncode}", file=sys.stderr)
            sys.exit(1)
            
    except Exception as e:
        print(f"[Recorder] Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Launch Playwright Recorder')
    parser.add_argument('--login-url', required=True, help='Login URL')
    parser.add_argument('--platform', required=True, help='Platform name')
    parser.add_argument('--component-type', required=True, help='Component type')
    parser.add_argument('--output-file', required=True, help='Output file path')
    
    args = parser.parse_args()
    
    launch_recorder(args.login_url, args.platform, args.component_type, args.output_file)

