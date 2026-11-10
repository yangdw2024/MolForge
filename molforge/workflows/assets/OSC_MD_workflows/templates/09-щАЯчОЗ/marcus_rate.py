#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
marcus_rate.py —— 标准 Marcus 电子转移速率计算模板

公式（非绝热极限）：
    k = (2*pi/hbar) * |V|^2 / sqrt(4*pi*lambda*kB*T)
        * exp[ -(dG + lambda)^2 / (4*lambda*kB*T) ]

输入参数来源：
    V       电子耦合 V_DA (eV)   <- 08 电子耦合（Q-Chem GMH）
    lambda  重组能 λ (eV)        <- 06 重组能（Gaussian 4 点法）
    dG      驱动力 ΔG (eV)       <- 前线轨道能级差 / 电荷态能量差
    T       温度 (K)

用法：
    python marcus_rate.py --V 0.98 --lam 0.82 --dG -0.77
    # 或读取 CSV：列 = name,V,lambda,dG  （--csv pairs.csv）
"""
import argparse
import csv
import math

# 常数
HBAR_EVS = 6.582119569e-16   # hbar (eV*s)
PI = math.pi

def marcus_k(V_eV, lam_eV, dG_eV, T=300.0):
    """返回 k (s^-1)"""
    # 玻尔兹曼常数 (eV/K)
    kB = 8.617333262e-5
    prefactor = (2 * PI / HBAR_EVS) * (V_eV ** 2) / math.sqrt(4 * PI * lam_eV * kB * T)
    exponent = -((dG_eV + lam_eV) ** 2) / (4 * lam_eV * kB * T)
    return prefactor * math.exp(exponent)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--V', type=float, help='电子耦合 V_DA (eV)')
    ap.add_argument('--lam', type=float, help='重组能 λ (eV)')
    ap.add_argument('--dG', type=float, help='驱动力 ΔG (eV)')
    ap.add_argument('--T', type=float, default=300.0, help='温度 (K)，默认 300')
    ap.add_argument('--csv', help='可选：CSV 文件，列 = name,V,lambda,dG（无表头）')
    args = ap.parse_args()

    if args.csv:
        with open(args.csv) as f:
            rows = list(csv.reader(f))
        print('name          V(eV)    lambda(eV)  dG(eV)    k(s^-1)')
        for r in rows:
            name, V, lam, dG = r[0], float(r[1]), float(r[2]), float(r[3])
            k = marcus_k(V, lam, dG, args.T)
            print(f'{name:<12s} {V:8.4f} {lam:10.4f} {dG:8.4f}  {k:.4e}')
    else:
        if None in (args.V, args.lam, args.dG):
            ap.error('请提供 --V --lam --dG（或 --csv）')
        k = marcus_k(args.V, args.lam, args.dG, args.T)
        print(f'k = {k:.4e} s^-1  (V={args.V}, λ={args.lam}, ΔG={args.dG}, T={args.T}K)')

if __name__ == '__main__':
    main()
