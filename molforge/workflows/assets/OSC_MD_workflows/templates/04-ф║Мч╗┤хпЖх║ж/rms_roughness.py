import os
import numpy as np

def read_density_map(file_path):
    # 从 .dat 文件读取密度图数据
    density_map = np.loadtxt(file_path)
    return density_map

def calculate_rms_roughness(density_map):
    # 计算均方根粗糙度
    rms_roughness = np.sqrt(np.mean(np.square(density_map - np.mean(density_map))))
    return rms_roughness

def process_folder(folder_path):
    # 获取文件夹中所有的文件路径
    file_paths = [os.path.join(folder_path, file) for file in os.listdir(folder_path) if file.endswith('.dat')]

    # 循环处理每个文件
    for file_path in file_paths:
        # 读取密度图数据
        density_map_data = read_density_map(file_path)

        # 计算均方根粗糙度
        rms_roughness_value = calculate_rms_roughness(density_map_data)

        # 输出均方根粗糙度值
        print(f'RMS Roughness for {file_path}: {rms_roughness_value}')

# 替换下面的文件夹路径为你的文件夹路径
folder_path = "D:/3/DENSI/md1"

# 处理文件夹中的所有文件
process_folder(folder_path)
