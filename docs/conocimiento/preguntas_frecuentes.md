# Preguntas frecuentes sobre el análisis

Explican cómo leer los resultados de DINAMO. Todo proviene de la metodología de la hoja LEEME y de las reglas del proyecto, no de fuentes externas.

## ¿Qué significa «se asocia con» y por qué nunca dice «causa»?
Una asociación indica que dos variables suben o bajan juntas entre las empresas. Con 40 empresas no es posible demostrar que una cosa provoque la otra, por eso DINAMO sólo habla de asociación y sugiere qué revisar.

## ¿Qué es el coeficiente rho de Spearman?
Es una medida de asociación entre -1 y 1 basada en el orden de los valores. Cerca de 0 significa que casi no hay relación; cerca de 1 o de -1 significa que se mueven juntas (en el mismo sentido o en sentido contrario). Se calcula con un dato por empresa.

## ¿Por qué se usa la mediana y no el promedio?
La mediana es el valor central: la mitad de las empresas está por debajo y la otra mitad por encima. No se distorsiona por una empresa con un valor extremo, lo cual es común en rotación y ausentismo.

## ¿Qué significa que una empresa «no reportó» un bimestre?
Significa que no entregó los datos de ese bimestre. En ese caso sus flujos (bajas, faltas) se tratan como faltantes y se completan con su propia mediana. Por eso los análisis consideran sólo los bimestres reportados.

## ¿Por qué algunas empresas se excluyen de un ranking?
Una empresa con muy pocos bimestres reportados puede aparecer en el primer lugar por un solo dato extraño. El ranking exige un mínimo de bimestres por empresa y lo advierte.

## ¿Qué es una evidencia y qué significa [E:id]?
Cada cifra que ve el usuario sale de un cálculo registrado, llamado evidencia, con su método y el número de empresas o bimestres usados. El identificador [E:id] enlaza la frase con ese cálculo para poder revisarlo.

## ¿Cuántas empresas y periodos cubre la base?
La base tiene 40 empresas y 7 bimestres, de Julio-Agosto 2024 a Julio-Agosto 2025, es decir 280 filas empresa por periodo. Fuente: hoja LEEME.

## ¿Los porcentajes están en escala de 0 a 1 o de 0 a 100?
En la base están en escala de 0 a 1 (0.15 significa 15 %). En las respuestas de DINAMO se muestran ya como porcentaje.

## ¿Qué diferencia hay entre rotación, ausentismo, incapacidad y contratación?
La rotación mide cuánta gente se va, el ausentismo cuántas faltas hay respecto a los días hábiles, la incapacidad los casos de incapacidad por empleado y la contratación cuánta gente se incorpora. Juntas muestran si una empresa crece o solo repone personal. Fuente: hoja VARIABLES_SELECCIONADAS.
