#!/usr/bin/env python3
"""
修复 SSL 证书验证问題的腳本
"""
import ssl
import certifi
import os

def fix_ssl_certificates():
    """修复 SSL 证书问题"""
    print("=== SSL 证书修复工具 ===")
    
    # 方法 1: 更新 certifi 套件
    print("1. 检查当前 certifi 证书包...")
    cert_file = certifi.where()
    print(f"certifi 证书文件位置: {cert_file}")
    print(f"证书文件存在: {os.path.exists(cert_file)}")
    
    # 方法 2: 检查 Python SSL 配置
    print("\n2. 检查 Python SSL 配置...")
    context = ssl.create_default_context()
    print(f"SSL 协议: {context.protocol}")
    print(f"验证模式: {context.verify_mode}")
    print(f"CA 证书路径: {context.ca_certs}")
    
    # 方法 3: 显示建议的修复命令
    print("\n3. 修复建议:")
    print("请依次执行以下命令:")
    print("pip install --upgrade certifi")
    print("/Applications/Python\\ 3.11/Install\\ Certificates.command")
    print("或者:")
    print("python -m pip install --upgrade certifi")
    
    return cert_file

if __name__ == "__main__":
    fix_ssl_certificates()
