filename = open('1.gro')
filename2 = open('A11.out','w')
num =  1
num2 = 1
HDO = ['C14','C15','C16','C17','C18','C19','C20','C21','C22','C23','C24','O1','C25','N5','C26','N6','C40','C41','C42','C43','C44','C45','C46','C47','C48','C49','O2','C50','C51','N7','C52','N8','Cl1','Cl2','Cl3','Cl4','C1','C2','C3','C4','C5','C6','N1','N2','S1','C7','C8','N3','N4','C9','S2','C10','C11','S3 ','C12','C13','S4 ','C31','C32','C33','S5 ','C34','C35','O3','O4',]
for line in filename.readlines():
    if num > 2:
        lineArr = line.strip().split()
        num+=1        
        if num > 38811:
            break
        if lineArr[1] in HDO:
            if num2 % 15 ==0:    
                filename2.write(lineArr[2]+'\n')  
                num2 += 1 
            else:  
                filename2.write(lineArr[2]+'  ')
                num2 += 1
            
    else:
        num+=1
     
