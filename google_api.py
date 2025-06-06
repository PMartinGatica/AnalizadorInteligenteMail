from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import pickle
from datetime import datetime

# Alcances necesarios para Google Drive y Google Sheets
SCOPES = [
    'https://www.googleapis.com/auth/drive.metadata.readonly',  # Para listar archivos de Drive
    'https://www.googleapis.com/auth/spreadsheets.readonly'     # Para leer datos de Sheets
]

def autenticar():
    """Autentica al usuario y devuelve las credenciales."""
    creds = None
    # El archivo token.pickle almacena las credenciales de acceso del usuario
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # Si no hay credenciales válidas, el usuario debe autenticarse
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=8080)
        # Guardar las credenciales para la próxima vez
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds

# Crear servicios para Google Drive y Google Sheets
def crear_servicios():
    creds = autenticar()
    drive_service = build('drive', 'v3', credentials=creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    return drive_service, sheets_service

# Ejemplo 1: Listar archivos en Google Drive
def listar_archivos(drive_service):
    results = drive_service.files().list(pageSize=10, fields="files(id, name)").execute()
    items = results.get('files', [])
    if not items:
        print('No se encontraron archivos.')
    else:
        print('Archivos:')
        for item in items:
            print(f"{item['name']} ({item['id']})")

# Ejemplo 2: Leer datos de una hoja de cálculo de Google Sheets
def leer_hoja_de_calculo(sheets_service, sheet_id, rango):
    sheet = sheets_service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range=rango).execute()
    valores = result.get('values', [])
    if not valores:
        print("No se encontraron datos.")
    else:
        for fila in valores:
            print(fila)

def buscar_archivos_drive(drive_service, query, max_results=10):
    """
    Busca archivos en Google Drive según los criterios especificados.
    
    Args:
        drive_service: Servicio de Google Drive autenticado
        query: String con la consulta de búsqueda
        max_results: Número máximo de resultados a devolver (default: 10)
    
    Returns:
        Lista de diccionarios con información de los archivos encontrados
    """
    try:
        results = drive_service.files().list(
            q=query,
            pageSize=max_results,
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink)"
        ).execute()
        
        files = results.get('files', [])
        
        # Formatear la fecha de modificación para cada archivo
        for file in files:
            if 'modifiedTime' in file:
                # Convertir la fecha a un formato más legible
                modified_time = datetime.strptime(
                    file['modifiedTime'], '%Y-%m-%dT%H:%M:%S.%fZ'
                )
                file['modifiedTime'] = modified_time.strftime('%Y-%m-%d %H:%M:%S')
        
        return files
        
    except Exception as e:
        print(f"Error al buscar archivos en Drive: {e}")
        return []

if __name__ == '__main__':
    creds = autenticar()
    print("Autenticación completada.")