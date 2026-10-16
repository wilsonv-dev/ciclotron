# Simulador de Ciclotrón

## Instrucciones de Inicio

# crear el entorno virtual
python -m venv venv
venv\Scripts\activate
# instalar dependencias 
pip install -r requirements.txt
# ejecutar backend
uvicorn backend.main:app --reload

uvicorn main:app --reload