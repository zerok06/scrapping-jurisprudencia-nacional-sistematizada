import csv
import json
import os
from pathlib import Path
from typing import List, Dict, Set, Any, Optional

def clean_string(val: Any) -> str:
    """
    Limpia una cadena: elimina espacios adicionales, saltos de línea molestos
    y normaliza caracteres vacíos.
    """
    if val is None:
        return ""
    text = str(val).strip()
    # Reemplazar múltiples espacios y retornos por espacios simples
    text = " ".join(text.split())
    return text

def clean_yaml_field(val: Any) -> str:
    """
    Sanitiza un valor para que pueda incluirse de forma segura en las
    comillas dobles del Front Matter YAML, escapando comillas y barras invertidas.
    """
    if val is None:
        return ""
    text = str(val).strip()
    # Escapar barras invertidas y comillas dobles
    text = text.replace('\\', '\\\\').replace('"', '\\"')
    # Eliminar retornos de carro
    text = text.replace('\n', ' ').replace('\r', '')
    return text

def load_json(filepath: Path) -> Optional[Any]:
    """
    Carga de forma segura un archivo JSON. Retorna None si no existe o está corrupto.
    """
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] No se pudo leer el archivo JSON {filepath.name}: {e}")
        return None

def save_json(filepath: Path, data: Any) -> bool:
    """
    Guarda datos en un archivo JSON en formato UTF-8 de forma segura.
    """
    try:
        # Escribir primero en un archivo temporal y luego renombrar para evitar corrupción por cortes de luz
        temp_path = filepath.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if filepath.exists():
            filepath.unlink()
        temp_path.rename(filepath)
        return True
    except Exception as e:
        print(f"[ERROR] No se pudo escribir el archivo JSON {filepath.name}: {e}")
        return False

def read_csv_records(filepath: Path) -> List[Dict[str, str]]:
    """
    Lee un archivo CSV y devuelve una lista de diccionarios.
    """
    if not filepath.exists():
        return []
    records = []
    try:
        with open(filepath, mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                for row in reader:
                    records.append(dict(row))
    except Exception as e:
        print(f"[ERROR] No se pudo leer el CSV {filepath.name}: {e}")
    return records

def write_csv_records(filepath: Path, fieldnames: List[str], records: List[Dict[str, Any]]) -> bool:
    """
    Sobrescribe un archivo CSV con los registros y campos provistos.
    """
    try:
        temp_path = filepath.with_suffix(".tmp")
        with open(temp_path, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                # Filtrar solo campos especificados en fieldnames para evitar ValueError
                row = {k: record.get(k, "") for k in fieldnames}
                writer.writerow(row)
        if filepath.exists():
            filepath.unlink()
        temp_path.rename(filepath)
        return True
    except Exception as e:
        print(f"[ERROR] No se pudo sobrescribir el CSV {filepath.name}: {e}")
        return False

def append_csv_records(filepath: Path, fieldnames: List[str], records: List[Dict[str, Any]], key_field: Optional[str] = None) -> int:
    """
    Agrega de forma idempotente nuevos registros a un archivo CSV.
    Si `key_field` se especifica, evita agregar duplicados comparando los valores de esa clave.
    Retorna la cantidad de nuevos registros insertados.
    """
    existing_keys: Set[str] = set()
    file_exists = filepath.exists()
    
    if file_exists and key_field:
        # Cargar claves existentes para evitar duplicados
        existing_records = read_csv_records(filepath)
        for r in existing_records:
            if key_field in r and r[key_field]:
                existing_keys.add(r[key_field])
                
    new_records_to_write = []
    for r in records:
        if key_field:
            val = r.get(key_field)
            if val and val in existing_keys:
                continue  # Duplicado, ignorar
            if val:
                existing_keys.add(val)
        new_records_to_write.append(r)
        
    if not new_records_to_write:
        return 0
        
    try:
        # Si no existe, lo creamos y escribimos cabeceras
        mode = "a" if file_exists else "w"
        with open(filepath, mode=mode, encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            for r in new_records_to_write:
                row = {k: r.get(k, "") for k in fieldnames}
                writer.writerow(row)
        return len(new_records_to_write)
    except Exception as e:
        print(f"[ERROR] Fallo al agregar registros al CSV {filepath.name}: {e}")
        return 0
