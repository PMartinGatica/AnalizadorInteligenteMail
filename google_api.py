from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import pickle

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

if __name__ == '__main__':
    creds = autenticar()
    print("Autenticación completada.")