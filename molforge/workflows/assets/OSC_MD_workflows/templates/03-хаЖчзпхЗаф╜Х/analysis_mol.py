#import random
import numpy as np
import pandas as pd
from scipy.optimize import leastsq
#import matplotlib.pyplot as plt
#from mpl_toolkits.mplot3d import Axes3D
from sklearn.metrics import mean_squared_error
from sklearn.linear_model import LinearRegression


def fit_plane(points_xyzs):
    
    vecs = [reg(points_xyzs),
            estimate_plane_with_leastsq(points_xyzs),
            plane_normal_vector_svd(points_xyzs)]
    errors = [evaluate(points_xyzs,vec) for vec in vecs]
    #print(errors)
    errors = np.array(errors)
    return vecs[np.argmin(errors[:,0])],errors[np.argmin(errors[:,0])]
    #print(vecs)
    #return vecs

def evaluate(points, normal_vector):
    pts = np.array(points)
    mean_pt = np.mean(pts,axis=0)
    distances = np.abs(np.dot(points-mean_pt,normal_vector) / np.linalg.norm(normal_vector))
    # 计算平均距离
    mean_distance = np.mean(distances)
    # 计算标准差
    std_distance = np.std(distances)
    return mean_distance, std_distance

def reg(pts):
    X = np.array(pts)
    reg = LinearRegression().fit(X[:, :2], X[:, 2].reshape(-1, 1))
    normal_vector = np.append(reg.coef_, -1)
    normal_vector = normal_vector / np.linalg.norm(normal_vector)
    y_pred = reg.predict(X[:, :2])
    #mse = mean_squared_error(X[:, 2].reshape(-1, 1), y_pred)
    #print(mse)
    return normal_vector

def plane_normal_vector_svd(points):
    points = np.asarray(points)
    mean = np.mean(points, axis=0)
    centered_points = points - mean
    _, _, vh = np.linalg.svd(centered_points, full_matrices=False)
    normal_vector = vh[-1, :]
    return normal_vector

#定义误差函数
def residuals(params, points, x, y, z):
    a, b, c, d = params
    dist = np.abs((a * x + b * y + c * z + d) / np.sqrt(a**2 + b**2 + c**2))
    return dist

#对指定的点进行拟合
def estimate_plane_with_leastsq(points):
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    params0 = [1, 1, 1, 1]
    result = leastsq(residuals, params0, args=(points, x, y, z))
    a, b, c, d = result[0]
    normal_vector = np.array([a, b, c]) / np.sqrt(a**2 + b**2 + c**2)
    return normal_vector

def calc_mcenter(xyzs,eles):
    atom_masses = {'C': 12.01, 'S': 32.06, 'H': 1.01, 
                   'O': 16.00, 'F': 19.00, 'N': 14.01, 'Cl': 35.45}
    x_total, y_total, z_total, total_mass = 0, 0, 0, 0
    for ele, (x, y, z) in zip(eles, xyzs):
        elem = ''.join([c for c in ele if c.isalpha()])
        mass = atom_masses[elem]
        x_total += x * mass
        y_total += y * mass
        z_total += z * mass
        total_mass += mass

    x_cm = x_total / total_mass
    y_cm = y_total / total_mass
    z_cm = z_total / total_mass
    return (x_cm,y_cm,z_cm)

def parse_data(gro_file_path:str,mols:list,fragments=None,velocity=False):
    import re
    import pandas as pd
    origin_file = open(gro_file_path)
    filelines = origin_file.readlines()
    origin_file.close()
    
    atom_line_indices=[];mol_indices=[];mol_types=[]
    ele_infos=[];atom_indices=[];atom_xyzs=[];j_list=[]
    patterns = [re.compile(r'[0-9]+{}'.format(mol)) for mol in mols]
    for i, line in enumerate(filelines):
        for j, pattern in enumerate(patterns):
            if pattern.search(line):
                mol=mols[j]
                j_list.append(j)
                break
        else: continue
        atom_line_indices.append(i)
        mol_indices.append(int(line[:5]))
        mol_types.append(mol)
        ele_infos.append(line[11:15].strip())
        atom_indices.append(int(line[15:20]))
        #print(line.split()[0:2])
        if velocity:
            atom_xyzs.append([float(num) for num in line.split()[-6:-3]])
            continue
        atom_xyzs.append([float(num) for num in line.split()[-3:]])
    
    atom_line_indices=np.array(atom_line_indices);mol_indices=np.array(mol_indices);mol_types=np.array(mol_types)
    ele_infos=np.array(ele_infos);atom_indices=np.array(atom_indices);atom_xyzs=np.array(atom_xyzs)
    
    #mols_dict={}
    unique_mol_indices = np.unique(mol_indices)
    indices_list=[]
    mol_type_list=[]
    ele_infos_list=[]
    mol_fragments_indices_list = []
    mol_fragments_eles_list = []
    mol_fragments_xyzs_list = []
    mol_fragments_vecs_list = []
    mol_fragments_vecs_err_list = []
    mol_fragments_mcenters_list = []
    for i, mol_index in enumerate(unique_mol_indices):
        indices = np.where(mol_indices==mol_index)[0]
        indices_list.append(indices)
        mol_type = mol_types[indices[0]]
        mol_type_list.append(mol_type)
        eles = ele_infos[indices]
        ele_infos_list.append(eles)
        if fragments:
            mol_fragments_eles = fragments[j_list[indices[0]]]
            mol_fragments_eles_list.append(mol_fragments_eles)
            mol_fragments_indices = [[j for j, item in enumerate(eles) 
                                      if item in mol_fragment_ele] 
                                     for mol_fragment_ele in mol_fragments_eles]
            mol_fragments_indices_list.append(mol_fragments_indices)
            mol_fragments_xyzs = [atom_xyzs[indices][mol_fragment_indices] 
                                  for mol_fragment_indices in mol_fragments_indices]
            mol_fragments_xyzs_list.append(mol_fragments_xyzs)
            mcenters = [calc_mcenter(xyzs, eles) for xyzs, eles in zip(
                mol_fragments_xyzs,mol_fragments_eles)]
            mol_fragments_mcenters_list.append(mcenters)
            vecs_errs_list = [fit_plane(pts) for pts in mol_fragments_xyzs]
            mol_fragments_vecs_list.append([vec_err[0] for vec_err in vecs_errs_list])
            mol_fragments_vecs_err_list.append([vec_err[1] for vec_err in vecs_errs_list])

            
    datasheet = pd.DataFrame({'mol_index':unique_mol_indices,
                            'line_indices':indices_list,
                            'xyzs':[atom_xyzs[indices] for indices in indices_list],
                            'elements':ele_infos_list,#[ele_infos[indices] for indices in indices_list],
                            'atom_indices':[atom_indices[indices] for indices in indices_list],
                            'mol_type':mol_type_list,#[mol_types[indices[0]] for indices in indices_list],
                            'vec':[fit_plane(pts) for pts in [atom_xyzs[indices] for indices in indices_list]],
                            'geo_center':[np.mean(atom_xyzs[indices],axis=0) for indices in indices_list]}
                            )
    if fragments:
        datasheet['fragments_inerindices'] = mol_fragments_indices_list
        datasheet['fragments_vecs'] = mol_fragments_vecs_list
        datasheet['fragments_vecs_err'] =mol_fragments_vecs_err_list
        datasheet['fragments_xyzs'] = mol_fragments_xyzs_list
        datasheet['fragments_mcenters'] =mol_fragments_mcenters_list
    return datasheet

def calc_angle(v1,v2):
    v1 = np.array(v1); v2 = np.array(v2)
    dot = np.dot(v1,v2)
    v1_norm = np.linalg.norm(v1); v2_norm = np.linalg.norm(v2)
    cos_angle = dot/(v1_norm*v2_norm)
    angle = np.arccos(cos_angle)
    return np.degrees(angle)

def read_md_cut(structure_file_name):
    import itertools
    #structure_file_name = 'md_cut.gro'
    PM6A = [['C1','C2','C3','C4','C5','C6','C7','C8','C9','C10','S1','S2','C28','C29','S7','C30','C31','C32','C33','S8','C34','C35'],
            ['C69','C70','S9','C71','C72','C73','C74','C75','C76','C77','C78','S10','C79','S11','C80','C81','S12','C82','C83','C84','C85'],
            ['C137','C138','S17','C139','C140','C141','C142','C143','C144','C145','C146','S18','C147','S19','C148','C149','S20','C150','C151','C152','C153','C154'],
            ['C205','C206','S25','C207','C208','C209','C210','C211','C212','C213','C214','S26','C215','S27','C216','C217','S28','C218','C219','C220','C221','C222'],
            ['C11','C12','C13','C14','C15','C16','C17','C18','C19','C20','C21','C22','C23','O1','O2','C24','C25','S6','C26','S3','S4','S5','C27','C38'],
            ['C87','C90','S13','C93','C94','C99','C104','S14','C107','C108','C109','C112','O3','C113','C114','C115','C116','O4','C117','S15','C118','S16','C120','C121'],
            ['C155','C158','S21','C161','C162','C167','C172','S22','C175','C176','C177','C180','O5','C181','C182','C183','C184','O6','C185','S23','C186','S24','C188','C189'],
            ['C239','C240','S29','C241','C242','C243','C244','S30','C245','C246','C247','C248','O7','C249','C250','C251','C252','O8','C253','S31','C254','S32','C256','C257']]
    HDOA = [['C1','C2','C3','C4','C5','C6','N1','N2','S1','C7','C8','N3','N4','C9','S2','C10','C11','S3','C12','C13','S4','C31','C32','C33','S5','C34','C35','O3','O4'],
            ['C40','C41','H17','C42','C43','C44','C45','C46','C47','C48','H18','C49','O2','C50','C51','N7','C52','N8','H89','Cl1','Cl4'],
            ['C14','C15','C16','C17','C18','C19','C20','C21','C22','C23','C24','H1','O1','C25','N5','C26','N6','H16','H88','Cl2','Cl3']]
    mol1='PM6';mol2='HDO'
    data = parse_data(structure_file_name,mols=[mol1,mol2],fragments=[PM6A,HDOA])
    #pd.options.display.max_columns = None
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_rows', None)
    #print(data.head(3))
    data.to_excel('{}_data.xlsx'.format(structure_file_name),index=False)
    #print(data[data['mol_type']=='DT'].index.values)
    #DT1=data[data['mol_type']=='PM6'].index.values[0]
    #plot_mol_vec_pic(data.loc[data['mol_type']=='PM6'].iloc[0])
    #plot_mol_fragments_vec_pic(data.loc[data['mol_type']=='HDO'].iloc[-2])
    M1data = data.loc[data['mol_type']==mol1]
    M2data = data.loc[data['mol_type']==mol2]
    #print(M2data.head(3))
    #print(M1data.head(3))
    #M1l = list(range(len(M1data))); M2l = list(range(len(M2data)))
    Mol_combs = list(itertools.product(M1data.index.tolist(),
                                       M2data.index.tolist()))
    Frag_combs = list(itertools.product(list(range(len(PM6A))),
                                        list(range(len(HDOA)))))

    M1list=[];M2list=[];M1F=[];M2F=[];disl=[];an=[]
    for Mol_comb in Mol_combs:
        for Frag_comb in Frag_combs:
            M1list.append(Mol_comb[0]+1);M1F.append(Frag_comb[0]+1)
            M2list.append(Mol_comb[1]+1);M2F.append(Frag_comb[1]+1)
            #print(Mol_comb,Frag_comb)
            mcenter1 = np.array(
                M1data.loc[Mol_comb[0],'fragments_mcenters'][Frag_comb[0]])
            #print(Mol_comb,Frag_comb,mcenter1)
            mcenter2 = np.array(
                M2data.loc[Mol_comb[1],'fragments_mcenters'][Frag_comb[1]])
            vec1 = M1data.loc[Mol_comb[0],'fragments_vecs'][Frag_comb[0]]
            vec2 = M2data.loc[Mol_comb[1],'fragments_vecs'][Frag_comb[1]]
            dis = np.linalg.norm(mcenter1-mcenter2);disl.append(dis)
            angle = calc_angle(vec1, vec2);an.append(angle)
#            results = results.append(pd.Series([Mol_comb,Frag_comb,dis,angle],
#                                               index=results.columns), 
#                                     ignore_index=True)
    results = pd.DataFrame(columns=['Molecule1', 'Molecule2',
                                    'M1Fragment','M2Fragment', 
                                    'distance', 
                                    'angle'],
                           data=np.array([M1list,M2list,M1F,M2F,disl,an]).T)       
    results.to_excel('{}_results.xlsx'.format(structure_file_name), sheet_name='Sheet1', index=False)
    #to_csv('results.csv',index=False)
    
if __name__ == '__main__':
    # input infos
    import os
    #folder = './'
    for file in os.listdir():
        if file.endswith('.gro'):
        #structure_file_name = 'md_cut.gro'
            print(file)
            read_md_cut(file)