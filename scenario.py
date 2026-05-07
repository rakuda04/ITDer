import pandas as pd
df = pd.read_csv('dataset/answers/insiders.csv')
r42 = df[df['dataset'].astype(str) == '4.2']
print(r42['scenario'].value_counts().sort_index())
print(r42[['scenario','user','details']].sort_values('scenario'))