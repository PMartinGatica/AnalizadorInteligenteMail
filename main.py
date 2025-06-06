# -*- coding: utf-8 -*-
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import json
import os
from datetime import datetime, timedelta
import re  # Importar re para limpieza de texto si es necesario
import random  # Importar random para generar colores aleatorios

# Importaciones de IA Generativa de Google
import google.generativeai as genai

# Importaciones de Flask
from flask import Flask, request, jsonify
from flask_cors import CORS

# Importaciones de Google API
from google_api import crear_servicios, listar_archivos, leer_hoja_de_calculo, buscar_archivos_drive
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# --- Configuración ---
IMAP_SERVER = 'imap.gmail.com'
EMAIL_USUARIO_FIJO = os.getenv('EMAIL_USUARIO')
CONTRASENA_APP_FIJA = os.getenv('CONTRASENA_APP')

# API Key de Google
GOOGLE_API_KEY_FIJA = os.getenv('GOOGLE_API_KEY')
GEMINI_API_KEY_CONFIGURADA = False
if GOOGLE_API_KEY_FIJA and GOOGLE_API_KEY_FIJA != "TU_GEMINI_API_KEY_AQUI":
    try:
        genai.configure(api_key=GOOGLE_API_KEY_FIJA)
        GEMINI_API_KEY_CONFIGURADA = True
        print("INFO: API Key de Google Gemini configurada directamente desde el código.")
    except Exception as e:
        print(f"ERROR: No se pudo configurar la API Key de Gemini: {e}")
        GEMINI_API_KEY_CONFIGURADA = False
else:
    print("ADVERTENCIA: La variable GOOGLE_API_KEY_FIJA no está configurada o es el valor placeholder. Los resúmenes IA con Gemini no funcionarán.")
    GEMINI_API_KEY_CONFIGURADA = False

# --- Inicialización de Flask ---
app = Flask(__name__)
CORS(app)  # Esto es crucial para resolver el error de CORS

def decodificar_asunto(header_string):
    """Decodifica el encabezado del correo, manejando diferentes codificaciones."""
    if not header_string:
        return ""
    decoded_parts = decode_header(header_string)
    asunto_decodificado = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            try:
                asunto_decodificado.append(part.decode(charset or 'utf-8', errors='replace'))
            except LookupError:
                asunto_decodificado.append(part.decode('utf-8', errors='replace'))
        else:
            asunto_decodificado.append(part)
    return "".join(asunto_decodificado)

def conectar_imap(email_usuario, contrasena_app):
    """
    Se conecta al servidor IMAP de Gmail usando las credenciales proporcionadas.
    Devuelve el objeto de conexión IMAP.
    """
    try:
        print(f"Conectando a {IMAP_SERVER} como {email_usuario}...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(email_usuario, contrasena_app)
        print("Conexión IMAP exitosa.")
        return mail
    except imaplib.IMAP4.error as e:
        print(f"Error al conectar o iniciar sesión en IMAP: {e}")
        return None
    except Exception as e:
        print(f"Ocurrió un error inesperado durante la conexión: {e}")
        return None

def buscar_correos_imap(mail_connection, asunto_buscado, fecha_desde_str=None, fecha_hasta_str=None):
    if not mail_connection:
        return []
    try:
        status, _ = mail_connection.select('inbox', readonly=True)
        if status != 'OK':
            print("Error al seleccionar la bandeja de entrada.")
            return []
        
        # Construcción del criterio de búsqueda
        criterios = []
        if asunto_buscado:
            criterios.append(f'(SUBJECT "{asunto_buscado}")')
        
        # Formato de fecha para IMAP: "DD-Mon-YYYY" (ej: "01-Jan-2023")
        if fecha_desde_str:
            try:
                fecha_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d')
                fecha_desde_imap = fecha_desde.strftime('%d-%b-%Y')
                criterios.append(f'(SINCE "{fecha_desde_imap}")')
            except ValueError:
                print(f"Formato de fecha_desde inválido: {fecha_desde_str}")

        if fecha_hasta_str:
            try:
                fecha_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d')
                fecha_hasta_imap = fecha_hasta.strftime('%d-%b-%Y')
                criterios.append(f'(BEFORE "{fecha_hasta_imap}")')
            except ValueError:
                print(f"Formato de fecha_hasta inválido: {fecha_hasta_str}")
        
        if not criterios:
            print("No hay criterios de búsqueda válidos (asunto o fechas).")
            if not asunto_buscado:
                return []

        search_query = " ".join(criterios)
        if not search_query.strip():
            return []

        print(f"Buscando correos con el criterio: {search_query}")
        
        status, email_uids_bytes_list = mail_connection.uid('search', None, search_query)

        if status != 'OK':
            print("Error en la búsqueda IMAP.")
            return []
            
        if not email_uids_bytes_list or not email_uids_bytes_list[0]:
            print("No se encontraron correos con los criterios especificados.")
            return []
        
        email_uids = email_uids_bytes_list[0].split()
        print(f"Se encontraron {len(email_uids)} UIDs de correos.")
        return email_uids
    except Exception as e:
        print(f"Ocurrió un error al buscar correos por IMAP: {e}")
        return []

def obtener_y_parsear_correo_imap(mail_connection, email_uid):
    if not mail_connection:
        return None
    try:
        status, data = mail_connection.uid('fetch', email_uid, '(RFC822)')
        if status != 'OK' or not data or not data[0]:
            print(f"Error al obtener el correo con UID {email_uid}")
            return None
        
        raw_email = data[0][1]
        mensaje_parseado = email.message_from_bytes(raw_email)
        return mensaje_parseado
    except Exception as e:
        print(f"Error al parsear correo UID {email_uid}: {e}")
        return None

def extraer_informacion_correo(mensaje_parseado, email_uid):
    """Extrae información relevante del correo parseado."""
    try:
        # Extraer información básica
        asunto = decodificar_asunto(mensaje_parseado.get('Subject', ''))
        remitente = mensaje_parseado.get('From', '')
        fecha_str = mensaje_parseado.get('Date', '')
        
        # Convertir fecha
        fecha_datetime = None
        if fecha_str:
            try:
                fecha_datetime = parsedate_to_datetime(fecha_str)
            except Exception as e:
                print(f"Error al parsear fecha: {e}")
        
        # Extraer cuerpo del correo
        cuerpo_texto = ""
        if mensaje_parseado.is_multipart():
            for part in mensaje_parseado.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        cuerpo_texto = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
                    except Exception as e:
                        print(f"Error al decodificar parte del correo: {e}")
        else:
            try:
                cuerpo_texto = mensaje_parseado.get_payload(decode=True).decode('utf-8', errors='ignore')
            except Exception as e:
                print(f"Error al decodificar correo: {e}")
        
        return {
            'uid': email_uid.decode() if isinstance(email_uid, bytes) else str(email_uid),
            'asunto': asunto,
            'remitente': remitente,
            'fecha': fecha_datetime.isoformat() if fecha_datetime else '',
            'cuerpo_texto_plano': cuerpo_texto[:1000]  # Limitar tamaño
        }
    except Exception as e:
        print(f"Error al extraer información del correo: {e}")
        return None

def generar_resumen_consolidado_ia(lista_textos_correos_ordenados):
    """
    Genera un resumen consolidado de una lista de textos de correos usando Gemini.
    """
    global GEMINI_API_KEY_CONFIGURADA
    if not GEMINI_API_KEY_CONFIGURADA:
        return "Resumen consolidado no disponible (API Key de Gemini no configurada)."
    
    if not lista_textos_correos_ordenados:
        return "No hay correos para resumir."

    texto_completo_para_resumir = "\n\n--- SIGUIENTE CORREO EN LA SECUENCIA ---\n\n".join(lista_textos_correos_ordenados)
    
    MAX_CHARS_FOR_SUMMARY = 180000
    if len(texto_completo_para_resumir) > MAX_CHARS_FOR_SUMMARY:
        texto_completo_para_resumir = texto_completo_para_resumir[:MAX_CHARS_FOR_SUMMARY] + "...[TEXTO TRUNCADO]"
    
    try:
        # Cambiar el modelo a uno disponible actualmente
        model = genai.GenerativeModel('gemini-1.5-flash')  # Cambio de gemini-pro a gemini-1.5-flash
        prompt = f"""
        Actúa como un analista experto en comunicaciones internas de una fábrica de ensamblaje de celulares (marca Motorola). Analiza cuidadosamente la siguiente secuencia de correos electrónicos. Tu objetivo es ayudarme a entender por completo el contenido, sin que se me escape ningún detalle relevante.

Genera un informe claro, ordenado y cronológico que incluya lo siguiente:

Un resumen del tema central que se discute, relacionado con el proceso de ensamblaje, componentes, logística, producción u otros aspectos técnicos o administrativos relevantes.

Un desglose de los puntos clave y argumentos mencionados por cada remitente.

Las decisiones tomadas o acciones propuestas en cada intercambio.

Una narrativa cronológica redactada naturalmente: incluye quién envió cada correo, la fecha, y qué dijo (por ejemplo: "El 6 de junio, Richard expresó preocupación por el faltante de placas madre...").

Datos adicionales que ayuden a comprender el contexto, como nombres de modelos, cantidades, plazos, problemas técnicos, propuestas, acuerdos o temas pendientes.

Redacta el informe de forma clara, completa y explicativa, como si se lo contaras a alguien que no leyó los correos. No omitas detalles, incluso si parecen pequeños.
        
        Correos a analizar:
        {texto_completo_para_resumir}
        
        Por favor, proporciona un resumen claro y estructurado.
        """
        
        response = model.generate_content(prompt)
        return response.text if response else "No se pudo generar el resumen."
    
    except Exception as e:
        print(f"Error al generar resumen con IA: {e}")
        return f"Error al generar resumen: {str(e)}"

@app.route('/api/buscar_correos', methods=['GET'])
def buscar_correos():
    try:
        asunto_a_buscar_param = request.args.get('asunto')
        fecha_desde_param = request.args.get('fecha_desde')
        fecha_hasta_param = request.args.get('fecha_hasta')

        if not asunto_a_buscar_param:
            return jsonify({"error": "El parámetro 'asunto' es requerido"}), 400

        print(f"Solicitud API recibida para buscar correos con asunto: '{asunto_a_buscar_param}', Desde: {fecha_desde_param}, Hasta: {fecha_hasta_param}")
        
        # Verificar que las credenciales estén configuradas
        if not EMAIL_USUARIO_FIJO or not CONTRASENA_APP_FIJA:
            error_msg = "Las credenciales de Gmail no están configuradas correctamente. Verifica las variables de entorno EMAIL_USUARIO y CONTRASENA_APP."
            print(f"ERROR: {error_msg}")
            return jsonify({"error": error_msg}), 500
        
        conexion_imap = conectar_imap(EMAIL_USUARIO_FIJO, CONTRASENA_APP_FIJA)
        if not conexion_imap:
            error_msg = "No se pudo conectar a Gmail vía IMAP. Verifica las credenciales y configuración de la cuenta."
            print(f"ERROR: {error_msg}")
            return jsonify({"error": error_msg}), 500

        uids_correos_encontrados = buscar_correos_imap(conexion_imap, asunto_a_buscar_param, fecha_desde_param, fecha_hasta_param)
        
        # Aunque no mostraremos correos individuales, los necesitamos para generar el resumen.
        todos_los_datos_extraidos = [] 
        textos_para_resumen_consolidado = []

        if uids_correos_encontrados:
            for i, email_uid in enumerate(uids_correos_encontrados):
                try:
                    mensaje_parseado = obtener_y_parsear_correo_imap(conexion_imap, email_uid)
                    if mensaje_parseado:
                        informacion = extraer_informacion_correo(mensaje_parseado, email_uid)
                        if informacion:
                            todos_los_datos_extraidos.append(informacion)
                except Exception as e:
                    print(f"Error al procesar correo UID {email_uid}: {e}")
                    continue
        
        if todos_los_datos_extraidos:
            try:
                # Ordenar por fecha para que el resumen tenga sentido cronológico
                todos_los_datos_extraidos.sort(key=lambda x: datetime.fromisoformat(x['fecha'].split('T')[0]) if x.get('fecha') else datetime.min, reverse=False)
                
                for info_correo_ordenado in todos_los_datos_extraidos:
                     # Formato más estructurado para la IA
                     texto_correo_info = (
                        f"FECHA: {info_correo_ordenado.get('fecha', 'N/A')}\n"
                        f"DE: {info_correo_ordenado.get('remitente', 'N/A')}\n"
                        f"ASUNTO: {info_correo_ordenado.get('asunto', 'N/A')}\n"
                        f"CUERPO:\n{info_correo_ordenado.get('cuerpo_texto_plano', '')}"
                     )
                     textos_para_resumen_consolidado.append(texto_correo_info)
            except Exception as e:
                print(f"Error al intentar ordenar u obtener textos de correos para el resumen: {e}. El resumen podría no estar en orden cronológico.")

        resumen_final_consolidado = "No se generó resumen consolidado."
        if GEMINI_API_KEY_CONFIGURADA and textos_para_resumen_consolidado:
            print(f"Intentando generar resumen consolidado para {len(textos_para_resumen_consolidado)} correos (ordenados cronológicamente).")
            try:
                resumen_final_consolidado = generar_resumen_consolidado_ia(textos_para_resumen_consolidado)
            except Exception as e:
                print(f"Error al generar resumen con IA: {e}")
                resumen_final_consolidado = f"Error al generar resumen: {str(e)}"
        elif not GEMINI_API_KEY_CONFIGURADA:
            resumen_final_consolidado = "Resumen consolidado no disponible (API Key de Gemini no configurada)."
        elif not textos_para_resumen_consolidado:
             resumen_final_consolidado = "No se encontraron correos para generar un resumen consolidado con los filtros aplicados."

        # Cerrar conexión IMAP de forma segura
        if conexion_imap:
            try:
                conexion_imap.close()
                conexion_imap.logout()
            except Exception as e:
                print(f"Error al cerrar conexión IMAP: {e}")
        
        respuesta_final = {
            "resumen_consolidado": resumen_final_consolidado,
            "total_correos": len(todos_los_datos_extraidos)
        }
        
        if not uids_correos_encontrados:
             respuesta_final["mensaje_general"] = f"No se encontraron correos con el asunto: '{asunto_a_buscar_param}' y los filtros de fecha aplicados."

        return jsonify(respuesta_final)
        
    except Exception as e:
        print(f"Error general en buscar_correos: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500

@app.route('/api/analizar_datos', methods=['GET'])
def analizar_datos():
    """Endpoint para analizar datos de una hoja de cálculo de Google Sheets"""
    sheet_id = request.args.get('sheet_id')
    rango = request.args.get('range')
    
    if not sheet_id or not rango:
        return jsonify({"error": "Es necesario proporcionar el ID de la hoja y el rango"}), 400
    
    try:
        # Crear los servicios de Google
        _, sheets_service = crear_servicios()
        
        # Obtener los datos de la hoja de cálculo
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=sheet_id, 
            range=rango
        ).execute()
        
        valores = result.get('values', [])
        
        if not valores:
            return jsonify({"error": "No se encontraron datos en la hoja de cálculo"}), 404
        
        # Procesar los datos para generar un gráfico
        # Este es un ejemplo simple que asume que la primera fila son encabezados
        # y la primera columna son etiquetas
        headers = valores[0][1:] if len(valores[0]) > 1 else []
        labels = [row[0] for row in valores[1:] if len(row) > 0]
        
        datasets = []
        for i, header in enumerate(headers):
            data_points = []
            for row in valores[1:]:
                # Obtener el valor numérico o 0 si no existe
                value = float(row[i+1]) if len(row) > i+1 and row[i+1] and row[i+1].replace('.','',1).isdigit() else 0
                data_points.append(value)
            
            # Generar un color aleatorio para el dataset
            color = f"rgba({random.randint(0, 255)}, {random.randint(0, 255)}, {random.randint(0, 255)}, 0.7)"
            
            datasets.append({
                "label": header,
                "data": data_points,
                "backgroundColor": color,
                "borderColor": color.replace("0.7", "1"),
                "borderWidth": 1
            })
        
        # Generar un resumen de los datos usando Google Gemini si está disponible
        resumen = ""
        if GEMINI_API_KEY_CONFIGURADA:
            try:
                prompt = f"""
                Analiza los siguientes datos y genera un breve resumen ejecutivo:
                
                Encabezados: {headers}
                Etiquetas: {labels}
                Valores: {valores[1:]}
                
                El resumen debe incluir:
                1. Tendencias principales observadas
                2. Valores máximos y mínimos
                3. Cualquier insight relevante de los datos
                4. Recomendaciones basadas en el análisis
                
                Usa formato Markdown para estructurar tu respuesta.
                """
                
                resumen = generar_resumen_consolidado_ia([prompt])
            except Exception as e:
                print(f"Error al generar resumen con Gemini: {e}")
        
        return jsonify({
            "titulo": f"Análisis de {rango}",
            "tipo_grafico": "bar",  # Puede ser 'bar', 'line', 'pie', etc.
            "labels": labels,
            "datasets": datasets,
            "resumen": resumen
        })
        
    except Exception as e:
        return jsonify({"error": f"Error al analizar datos: {str(e)}"}), 500

@app.route('/api/analizar_bbdd', methods=['GET'])
def analizar_bbdd():
    """Endpoint para analizar la base de datos de fallas específica"""
    try:
        # Usar un ID de hoja específico
        sheet_id = "1UeO_fORpKELd15gOzitXD3VMCZPMSIQpR6aX9A-eyaA"
        rango = "Import!A1:Z"  # Ajustar según sea necesario
        
        # Crear los servicios de Google
        _, sheets_service = crear_servicios()
        
        # Obtener los datos de la hoja de cálculo
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=sheet_id, 
            range=rango
        ).execute()
        
        valores = result.get('values', [])
        
        if not valores or len(valores) <= 1:
            return jsonify({"error": "No se encontraron datos suficientes"}), 404
        
        # Obtener índices de columnas importantes (insensible a mayúsculas/minúsculas)
        headers = valores[0]
        headers_lower = [h.lower() if isinstance(h, str) else "" for h in headers]
        
        try:
            # Buscar columnas por nombre (insensible a mayúsculas/minúsculas)
            track_id_index = -1
            family_index = -1
            test_code_index = -1
            proceso_index = -1;
            
            for i, header in enumerate(headers_lower):
                if header == 'trackid':
                    track_id_index = i
                elif header == 'family':
                    family_index = i
                elif header == 'testcode':
                    test_code_index = i
                elif header == 'process':
                    proceso_index = i
            
            # Verificar que se encontraron todas las columnas
            if track_id_index == -1:
                return jsonify({"error": "No se encontró la columna 'TrackID'"}), 400
            if family_index == -1:
                return jsonify({"error": "No se encontró la columna 'Family'"}), 400
            if test_code_index == -1:
                return jsonify({"error": "No se encontró la columna 'TestCode'"}), 400
            if proceso_index == -1:
                return jsonify({"error": "No se encontró la columna 'Process'"}), 400
                
        except Exception as e:
            return jsonify({"error": f"Error al procesar encabezados: {str(e)}"}), 400
        
        print(f"Columnas encontradas: TrackID={track_id_index}, Family={family_index}, TestCode={test_code_index}, Process={proceso_index}")
        
        # Procesar datos para los gráficos
        # 1. Conteo por familia
        family_counts = {}
        for row in valores[1:]:  # Saltamos los encabezados
            if len(row) > family_index:  # Aseguramos que la fila tenga los datos necesarios
                family = row[family_index] if row[family_index] else "Sin Familia"
                if family in family_counts:
                    family_counts[family] += 1
                else:
                    family_counts[family] = 1
        
        # Obtener top 5 familias
        top_families = sorted(family_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # 2. Conteo por TestCode
        testcode_counts = {}
        for row in valores[1:]:
            if len(row) > test_code_index:
                testcode = row[test_code_index] if len(row) > test_code_index and row[test_code_index] else "Sin TestCode"
                if testcode in testcode_counts:
                    testcode_counts[testcode] += 1
                else:
                    testcode_counts[testcode] = 1
        
        # Obtener top 5 TestCodes
        top_testcodes = sorted(testcode_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # 3. Conteo por Proceso
        proceso_counts = {}
        for row in valores[1:]:
            if len(row) > proceso_index:
                proceso = row[proceso_index] if len(row) > proceso_index and row[proceso_index] else "Sin Proceso"
                if proceso in proceso_counts:
                    proceso_counts[proceso] += 1
                else:
                    proceso_counts[proceso] = 1
        
        # Obtener top procesos
        top_procesos = sorted(proceso_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # 4. Top TestCodes por cada una de las 5 familias principales
        testcodes_by_family = {}
        for family_name, _ in top_families:
            testcodes_by_family[family_name] = {}
        
        for row in valores[1:]:
            if len(row) > max(family_index, test_code_index):
                family = row[family_index] if row[family_index] else "Sin Familia"
                if family in testcodes_by_family:
                    testcode = row[test_code_index] if len(row) > test_code_index and row[test_code_index] else "Sin TestCode"
                    if testcode in testcodes_by_family[family]:
                        testcodes_by_family[family][testcode] += 1
                    else:
                        testcodes_by_family[family][testcode] = 1
        
        # Para cada familia, obtener sus top 5 TestCodes
        family_top_testcodes = {}
        for family in testcodes_by_family:
            family_top_testcodes[family] = sorted(testcodes_by_family[family].items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Preparar datos para el frontend
        charts_data = {
            "total_registros": len(valores) - 1,
            "top_families": {
                "labels": [x[0] for x in top_families],
                "data": [x[1] for x in top_families],
                "tipo": "bar",
                "titulo": "Top 5 Familias por Cantidad de Fallas"
            },
            "top_testcodes": {
                "labels": [x[0] for x in top_testcodes],
                "data": [x[1] for x in top_testcodes],
                "tipo": "pie",
                "titulo": "Top 5 TestCodes más Frecuentes"
            },
            "top_procesos": {
                "labels": [x[0] for x in top_procesos],
                "data": [x[1] for x in top_procesos],
                "tipo": "line",
                "titulo": "Top 5 Procesos por Cantidad de Fallas"
            },
            "testcodes_by_family": {
                "families": list(family_top_testcodes.keys()),
                "datasets": []
            }
        }
        
        # Preparar datos para gráfico de barras agrupadas de TestCodes por Familia
        all_testcodes = set()
        for family in family_top_testcodes:
            for testcode, _ in family_top_testcodes[family]:
                all_testcodes.add(testcode)
        
        for testcode in all_testcodes:
            dataset = {
                "label": testcode,
                "data": []
            }
            for family in family_top_testcodes:
                found = False
                for tc, count in family_top_testcodes[family]:
                    if tc == testcode:
                        dataset["data"].append(count)
                        found = True
                        break
                if not found:
                    dataset["data"].append(0)
            
            # Color aleatorio para cada dataset
            color = f"rgba({random.randint(0, 255)}, {random.randint(0, 255)}, {random.randint(0, 255)}, 0.7)"
            dataset["backgroundColor"] = color
            dataset["borderColor"] = color.replace("0.7", "1")
            dataset["borderWidth"] = 1
            
            charts_data["testcodes_by_family"]["datasets"].append(dataset)
        
        return jsonify(charts_data)
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())  # Imprime el error completo en la consola
        return jsonify({"error": f"Error al analizar datos: {str(e)}"}), 500

@app.route('/api/asistente_consulta', methods=['POST'])
def asistente_consulta():
    try:
        data = request.json
        user_query = data.get('query', '')
        
        # Si la consulta es sobre búsqueda de archivos
        if "archivos" in user_query.lower() or "drive" in user_query.lower():
            # Código existente para búsqueda de archivos...
            pass
            
        # Si es otro tipo de consulta, usa el modelo generativo
        model = genai.GenerativeModel('gemini-1.5-flash')  # Cambio aquí también
        response = model.generate_content(user_query)
        
        return jsonify({
            "response": response.text if hasattr(response, 'text') else "No se pudo generar una respuesta"
        })
        
    except Exception as e:
        print(f"Error en asistente_consulta: {str(e)}")
        return jsonify({"error": f"Error al procesar consulta: {str(e)}"}), 500

@app.route('/api/test_connection', methods=['GET'])
def test_connection():
    try:
        print(f"Probando conexión con: {EMAIL_USUARIO_FIJO}")
        print(f"Contraseña (primeros 4 chars): {CONTRASENA_APP_FIJA[:4] if CONTRASENA_APP_FIJA else 'None'}...")
        
        if not EMAIL_USUARIO_FIJO or not CONTRASENA_APP_FIJA:
            return jsonify({"status": "error", "message": "Credenciales no configuradas"}), 400
        
        conexion = conectar_imap(EMAIL_USUARIO_FIJO, CONTRASENA_APP_FIJA)
        if conexion:
            conexion.close()
            conexion.logout()
            return jsonify({"status": "success", "message": "Conexión IMAP exitosa"})
        else:
            return jsonify({"status": "error", "message": "Falló la conexión IMAP"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
