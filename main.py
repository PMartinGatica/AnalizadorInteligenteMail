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
from google_api import crear_servicios, listar_archivos, leer_hoja_de_calculo
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
                fecha_desde_obj = datetime.strptime(fecha_desde_str, '%Y-%m-%d')
                criterios.append(f'(SINCE {fecha_desde_obj.strftime("%d-%b-%Y")})')
            except ValueError:
                print(f"Advertencia: Formato de fecha_desde incorrecto: {fecha_desde_str}. Se ignorará.")

        if fecha_hasta_str:
            try:
                fecha_hasta_obj = datetime.strptime(fecha_hasta_str, '%Y-%m-%d')
                fecha_limite_superior = fecha_hasta_obj + timedelta(days=1)
                criterios.append(f'(BEFORE {fecha_limite_superior.strftime("%d-%b-%Y")})')
            except ValueError:
                print(f"Advertencia: Formato de fecha_hasta incorrecto: {fecha_hasta_str}. Se ignorará.")
        
        if not criterios:
            print("No hay criterios de búsqueda válidos (asunto o fechas).")
            if not asunto_buscado:
                print("El asunto es requerido para la búsqueda.")
                return []

        search_query = " ".join(criterios)
        if not search_query.strip():
            print("Criterio de búsqueda final vacío. No se realizará la búsqueda.")
            return []

        print(f"Buscando correos con el criterio: {search_query}")
        
        status, email_uids_bytes_list = mail_connection.uid('search', None, search_query)

        if status != 'OK':
            print(f"Error durante la búsqueda IMAP: {status}")
            return []
        if not email_uids_bytes_list or not email_uids_bytes_list[0]:
            print("No se encontraron UIDs de correos que coincidan con los criterios.")
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
        if status == 'OK':
            raw_email = data[0][1]
            email_message = email.message_from_bytes(raw_email)
            return email_message
        else:
            print(f"Error al obtener el correo con UID {email_uid.decode()}: {status}")
            return None
    except Exception as e:
        print(f"Ocurrió un error al obtener o parsear el correo UID {email_uid.decode()}: {e}")
        return None

def generar_resumen_consolidado_ia(lista_textos_correos_ordenados):
    """
    Genera un resumen consolidado de una lista de textos de correos (ordenados cronológicamente) usando Gemini.
    """
    global GEMINI_API_KEY_CONFIGURADA
    if not GEMINI_API_KEY_CONFIGURADA:
        return "Resumen consolidado no disponible (API Key de Gemini no configurada)."
    if not lista_textos_correos_ordenados:
        return "No hay contenido de correos para generar un resumen consolidado."

    texto_completo_para_resumir = "\n\n--- SIGUIENTE CORREO EN LA SECUENCIA ---\n\n".join(lista_textos_correos_ordenados)
    
    MAX_CHARS_FOR_SUMMARY = 180000
    if len(texto_completo_para_resumir) > MAX_CHARS_FOR_SUMMARY:
        print(f"ADVERTENCIA: El texto concatenado ({len(texto_completo_para_resumir)} chars) excede el límite de {MAX_CHARS_FOR_SUMMARY} chars. Se truncará.")
        texto_completo_para_resumir = texto_completo_para_resumir[:MAX_CHARS_FOR_SUMMARY]

    print(f"Generando resumen CONSOLIDADO IA con Gemini para texto de {len(texto_completo_para_resumir)} caracteres...")

    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        prompt = (
            "Eres un analista experto y un excelente comunicador. Tu tarea es analizar la siguiente secuencia de correos electrónicos, proporcionados en orden cronológico, "
            "y generar un informe narrativo que describa la evolución de los eventos, discusiones, decisiones clave y acciones resultantes. "
            "El informe debe leerse como un flujograma coherente de los acontecimientos.\n\n"
            "**Estructura y Tono del Informe:**\n"
            "- Comienza con un título general y conciso que capture la esencia del tema tratado en los correos.\n"
            "- Continúa con una narrativa fluida y cronológica. En lugar de usar encabezados rígidos como 'Introducción' o 'Desarrollo', integra esta información de manera natural en el flujo del texto.\n"
            "- Para cada desarrollo importante, identifica quién hizo o dijo qué, cuándo ocurrió (si es relevante y distintivo), y cuál fue el impacto o la información clave.\n"
            "- Utiliza párrafos bien formados para separar ideas o etapas distintas en la cronología. Puedes usar listas con viñetas si es apropiado para enumerar acciones o puntos específicos dentro de un desarrollo.\n"
            "- Destaca las decisiones cruciales, los problemas que surgieron, las soluciones que se propusieron o implementaron, y cualquier acción que quede pendiente al final de la secuencia.\n"
            "- El lenguaje debe ser profesional, claro, y preciso. Presta atención a la gramática, puntuación y ortografía.\n"
            "- El objetivo es que alguien que no leyó los correos pueda entender rápidamente qué sucedió, cómo evolucionó la situación y cuál es el estado actual.\n"
            "- Si es posible, utiliza Markdown sutil para enfatizar puntos clave (como **texto en negrita** para nombres de proyectos o decisiones importantes, o *cursiva* para citas breves o términos específicos) y para listas.\n\n"
            "**Contenido a Extraer y Presentar:**\n"
            "- El tema o proyecto principal.\n"
            "- Los participantes clave y sus roles (si se deducen).\n"
            "- La secuencia de eventos y comunicaciones.\n"
            "- Problemas identificados y cómo se abordaron.\n"
            "- Decisiones tomadas.\n"
            "- Resultados o estado actual del tema.\n"
            "- Cualquier tarea o acción pendiente.\n\n"
            "Analiza la siguiente secuencia de correos:\n\n"
            f"{texto_completo_para_resumir}\n\n"
            "---\n**Informe Cronológico Detallado:**"
        )
        
        generation_config = genai.types.GenerationConfig(
            candidate_count=1,
            max_output_tokens=2500,
            temperature=0.6,
        )

        response = model.generate_content(prompt, generation_config=generation_config)

        if response.parts:
            resumen = response.text.strip()
            resumen = re.sub(r'\n\s*\n', '\n\n', resumen)
            print("Resumen CONSOLIDADO IA con Gemini generado.")
            return resumen
        elif response.prompt_feedback and response.prompt_feedback.block_reason:
            block_reason_message = f"Contenido bloqueado por Gemini. Razón: {response.prompt_feedback.block_reason}"
            if response.prompt_feedback.safety_ratings:
                block_reason_message += f" Ratings: {response.prompt_feedback.safety_ratings}"
            print(f"ADVERTENCIA: {block_reason_message}")
            return f"Resumen consolidado no generado: {block_reason_message}"
        else:
            resumen = response.text.strip() if hasattr(response, 'text') and response.text else "No se pudo generar el resumen consolidado (respuesta vacía de Gemini)."
            if not resumen.startswith("No se pudo generar"):
                 print("Resumen CONSOLIDADO IA con Gemini generado (respuesta sin 'parts' pero con 'text').")
            else:
                 print(f"ADVERTENCIA: {resumen} Respuesta completa: {response}")
            return resumen
            
    except Exception as e:
        print(f"Error de API de Google Gemini al generar resumen CONSOLIDADO: {e}")
        return f"Error al generar resumen CONSOLIDADO IA con Gemini: {str(e)}"

def extraer_informacion_correo(email_message, email_uid):
    if not email_message:
        return None

    fecha_str = decodificar_asunto(email_message.get("Date"))
    fecha_iso = fecha_str
    if fecha_str:
        try:
            dt_obj = parsedate_to_datetime(fecha_str)
            if dt_obj:
                fecha_iso = dt_obj.isoformat()
        except Exception as e:
            print(f"No se pudo parsear la fecha '{fecha_str}': {e}. Usando valor original.")

    informacion_extraida = {
        "id_mensaje_uid": email_uid.decode() if isinstance(email_uid, bytes) else str(email_uid),
        "fecha": fecha_iso,
        "remitente": decodificar_asunto(email_message.get("From")),
        "asunto": decodificar_asunto(email_message.get("Subject")),
        "cuerpo_texto_plano": ""
    }

    cuerpo_bruto = ""
    if email_message.is_multipart():
        for part in email_message.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == 'text/plain' and 'attachment' not in content_disposition:
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    cuerpo_bruto = part.get_payload(decode=True).decode(charset, errors='replace')
                    break 
                except Exception as e:
                    print(f"No se pudo decodificar una parte del cuerpo (text/plain) para UID {informacion_extraida['id_mensaje_uid']}: {e}")
                    cuerpo_bruto = "[Cuerpo no decodificable o error de charset]"
    else:
        content_type = email_message.get_content_type()
        if content_type == 'text/plain':
            try:
                charset = email_message.get_content_charset() or 'utf-8'
                cuerpo_bruto = email_message.get_payload(decode=True).decode(charset, errors='replace')
            except Exception as e:
                print(f"No se pudo decodificar el cuerpo (no multipart) para UID {informacion_extraida['id_mensaje_uid']}: {e}")
                cuerpo_bruto = "[Cuerpo no decodificable o error de charset]"

    cuerpo_limpio = cuerpo_bruto
    marcadores_corte = [
        "LA INFORMACION AQUI CONTENIDA ES CONFIDENCIAL",
        "THE INFORMATION CONTAINED IN THIS E-MAIL IS PRIVILEGED",
        "www.newsan.com.ar",
        "-- \r\n\r\n[image: photo]",
        "Cordialmente,", "Saludos,", "Atentamente,", "Regards,", "Best regards,",
        "--------------------------------------------------------------------",
        "____________________________________________________________________"
    ]
    posicion_corte = len(cuerpo_limpio)
    for marcador in marcadores_corte:
        idx = cuerpo_limpio.find(marcador)
        if idx != -1 and idx < posicion_corte:
            posicion_corte = idx
    if posicion_corte < len(cuerpo_limpio):
        cuerpo_limpio = cuerpo_limpio[:posicion_corte]
    
    informacion_extraida["cuerpo_texto_plano"] = cuerpo_limpio.strip()
    return informacion_extraida

@app.route('/api/buscar_correos', methods=['GET'])
def buscar_correos():
    asunto_a_buscar_param = request.args.get('asunto')
    fecha_desde_param = request.args.get('fecha_desde')
    fecha_hasta_param = request.args.get('fecha_hasta')

    if not asunto_a_buscar_param:
        return jsonify({"error": "El parámetro 'asunto' es requerido"}), 400

    print(f"Solicitud API recibida para buscar correos con asunto: '{asunto_a_buscar_param}', Desde: {fecha_desde_param}, Hasta: {fecha_hasta_param}")
    
    conexion_imap = conectar_imap(EMAIL_USUARIO_FIJO, CONTRASENA_APP_FIJA)
    if not conexion_imap:
        return jsonify({"error": "No se pudo conectar a Gmail vía IMAP."}), 500

    uids_correos_encontrados = buscar_correos_imap(conexion_imap, asunto_a_buscar_param, fecha_desde_param, fecha_hasta_param)
    
    # Aunque no mostraremos correos individuales, los necesitamos para generar el resumen.
    todos_los_datos_extraidos = [] 
    textos_para_resumen_consolidado = []

    if uids_correos_encontrados:
        for i, email_uid in enumerate(uids_correos_encontrados):
            mensaje_parseado = obtener_y_parsear_correo_imap(conexion_imap, email_uid)
            if mensaje_parseado:
                informacion = extraer_informacion_correo(mensaje_parseado, email_uid)
                if informacion:
                    todos_los_datos_extraidos.append(informacion)
    
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
    global GEMINI_API_KEY_CONFIGURADA
    if GEMINI_API_KEY_CONFIGURADA and textos_para_resumen_consolidado:
        print(f"Intentando generar resumen consolidado para {len(textos_para_resumen_consolidado)} correos (ordenados cronológicamente).")
        resumen_final_consolidado = generar_resumen_consolidado_ia(textos_para_resumen_consolidado)
    elif not GEMINI_API_KEY_CONFIGURADA:
        resumen_final_consolidado = "Resumen consolidado no disponible (API Key de Gemini no configurada)."
    elif not textos_para_resumen_consolidado:
         resumen_final_consolidado = "No se encontraron correos para generar un resumen consolidado con los filtros aplicados."

    if conexion_imap:
        try:
            conexion_imap.close()
        except: pass
        finally:
            try:
                conexion_imap.logout()
            except: pass
    
    respuesta_final = {
        "resumen_consolidado": resumen_final_consolidado
    }
    if not uids_correos_encontrados and not (GEMINI_API_KEY_CONFIGURADA and textos_para_resumen_consolidado):
         respuesta_final["mensaje_general"] = f"No se encontraron correos con el asunto: '{asunto_a_buscar_param}' y los filtros de fecha aplicados."

    return jsonify(respuesta_final)

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
    """Endpoint para procesar consultas del asistente IA"""
    try:
        # Obtener los datos de la consulta
        data = request.json
        if not data or 'query' not in data:
            return jsonify({"error": "La consulta es requerida"}), 400
        
        user_query = data.get('query')
        context = data.get('context', [])
        analysis_data = data.get('analysisData', {})
        
        # Verificar si tenemos datos de análisis
        if not analysis_data:
            return jsonify({"response": "Lo siento, no tengo datos de análisis disponibles para responder a tu pregunta."}), 200
        
        # Determinar el tipo de análisis y construir el prompt adecuado
        analysis_type = analysis_data.get('tipo', '')
        
        if analysis_type == "informe_correo":
            # Prompt para informe de correo
            prompt = f"""
            Eres un asistente analítico especializado en resúmenes de correos electrónicos. 
            Te han proporcionado el siguiente informe generado a partir de un hilo de correos con asunto: "{analysis_data.get('asunto', 'No especificado')}".
            
            El contenido del informe es:
            
            ```
            {analysis_data.get('contenido', 'Informe no disponible')}
            ```
            
            HISTORIAL DE LA CONVERSACIÓN:
            {context}
            
            CONSULTA DEL USUARIO: {user_query}
            
            Responde a la consulta del usuario basándote en el informe proporcionado.
            - Sé específico y utiliza información concreta del informe
            - Si te preguntan por algo que no está en el informe, indícalo claramente
            - Utiliza Markdown para formatear la respuesta cuando sea útil
            
            Tu respuesta:
            """
        else:
            # Prompt existente para análisis de datos (conservar el código original)
            formatted_data = json.dumps(analysis_data, indent=2)
            prompt = f"""
            Eres un asistente analítico especializado en datos de fallas técnicas. Te han proporcionado los siguientes datos de análisis:
            
            ```json
            {formatted_data}
            ```
            
            Estos datos contienen información sobre:
            - Las 5 familias con más fallas (conteo de TrackID)
            - Los 5 TestCodes más frecuentes
            - Los 5 procesos con más fallas
            - Información detallada sobre los TestCodes por cada familia principal
            
            HISTORIAL DE LA CONVERSACIÓN:
            {context}
            
            CONSULTA DEL USUARIO: {user_query}
            
            Responde a la consulta del usuario de forma clara y concisa, utilizando los datos proporcionados.
            - Menciona números específicos y porcentajes cuando sea relevante
            - Si te preguntan por datos que no están disponibles, indícalo claramente
            - Usa un tono conversacional pero profesional
            - Utiliza Markdown para formatear la respuesta cuando sea útil (negritas, listas, etc.)
            - Si te preguntan por un análisis que no tienes los datos suficientes para hacer, sugiere qué información adicional sería útil
            
            Tu respuesta:
            """
            
        # El resto del código permanece igual
        # ...
        
        # Hacer la consulta a Gemini
        try:
            model = genai.GenerativeModel('gemini-1.5-flash-latest')
            response = model.generate_content(prompt)
            
            assistant_response = response.text.strip() if hasattr(response, 'text') and response.text else "No pude generar una respuesta adecuada con los datos disponibles."
            
            return jsonify({"response": assistant_response}), 200
            
        except Exception as e:
            print(f"Error al generar respuesta con Gemini: {e}")
            return jsonify({"response": f"Lo siento, no pude procesar tu consulta debido a un error: {str(e)}"}), 200
            
    except Exception as e:
        return jsonify({"error": f"Error al procesar consulta: {str(e)}"}), 500

if __name__ == '__main__':
    if not EMAIL_USUARIO_FIJO or not CONTRASENA_APP_FIJA or not GOOGLE_API_KEY_FIJA or GOOGLE_API_KEY_FIJA == "TU_GEMINI_API_KEY_AQUI":
        print("ADVERTENCIA: Revisa la configuración de EMAIL_USUARIO_FIJO, CONTRASENA_APP_FIJA o GOOGLE_API_KEY_FIJA en el script.")
    
    print("Iniciando servidor Flask en http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=True)
