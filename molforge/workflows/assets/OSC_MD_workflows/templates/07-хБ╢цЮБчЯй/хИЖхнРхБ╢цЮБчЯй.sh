#!/bin/bash

# ɾ��֮ǰ���ܲ����Ļ����ļ�
rm -f all_outputs.txt

# ��¼��ǰ�������ļ�����
nfile=0

# �������� .fchk �ļ�
for inf in *.fchk
do
    ((nfile++))
    echo "Processing $inf ..."

    # ��ȡ�ļ�������������չ������Ϊ����ļ���
    base_name=$(basename "$inf" .fchk)
    output_file="${base_name}_output.txt"
    multipole_file="${base_name}_multipole.txt"

    # ���� Multiwfn ���������ļ�����������浽��Ӧ������ļ�
    Multiwfn "$inf" -silent << EOF > "$output_file"
15
-1
3
-5
1-199
2
2
EOF

    # �� Multiwfn ִ���ڼ䣬��׽ multipole ��������浽ָ���ļ�
    if [ -f multipole.txt ]; then
        mv multipole.txt "$multipole_file"
        echo "Saved multipole file as $multipole_file"
    else
        echo "Warning: multipole.txt not found for $inf"
    fi

    # ����ǰ�ļ���������ӵ� all_outputs.txt ��
    cat "$output_file" >> all_outputs.txt
done

echo "Done! All individual results and multipole files have been saved."
echo "Totally $nfile files were processed."
