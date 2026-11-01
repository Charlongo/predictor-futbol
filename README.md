# Mi Predictor de Fútbol — versión privada para iPhone

Esta es una aplicación web adaptable a móviles (Streamlit). No es una app nativa de App Store. Se puede abrir en Safari y añadir a la pantalla de inicio.

## Funciones
- Acceso con contraseña.
- Calendario de partidos por fecha.
- Consulta de últimos 10 resultados de los equipos.
- Modelo Poisson básico para goles, ambos marcan, 1X2 y resultados exactos probables.
- Comparación entre probabilidades estimadas y cuotas introducidas manualmente.
- Historial de predicciones guardadas y exportación CSV.
- Importación de CSV autorizados.
- Caché para reducir peticiones repetidas.

## Antes de usarla
La app todavía no está publicada ni tiene una API key configurada. La contraseña y la API key deben añadirse como secretos en el servicio de alojamiento; no las pongas en archivos públicos.

## Despliegue gratuito sugerido: Streamlit Community Cloud
1. Crea un repositorio **privado** en GitHub y sube `app.py`, `requirements.txt` y `README.md`.
2. En Streamlit Community Cloud, conecta GitHub y despliega `app.py`.
3. En la configuración de Secrets del despliegue, añade:
   ```toml
   APP_PASSWORD = "elige-una-contraseña-larga-y-única"
   API_FOOTBALL_KEY = "tu-clave-de-api-football"
   ```
4. Guarda los secretos y reinicia la aplicación.
5. Prueba que aparece la pantalla de contraseña y que los partidos cargan.

**Importante sobre privacidad:** el control de contraseña de esta app limita la interfaz, pero el alojamiento, la URL y el tratamiento de datos dependen del proveedor. Para información especialmente sensible, usa un alojamiento con autenticación robusta. No publiques la API key en GitHub. Un repositorio privado no convierte automáticamente en privada la URL pública de una app desplegada.

## Añadir al iPhone
1. Abre la URL de la app en Safari.
2. Pulsa Compartir.
3. Selecciona “Añadir a pantalla de inicio”.
4. Ponle el nombre “Mi Predictor”.

## Fuente estadística
API-Football: https://www.api-football.com/
Documentación: https://www.api-football.com/documentation-v3

La cobertura, el histórico, las cuotas, los límites y el coste dependen del plan vigente. No se garantiza integración directa con Futdatos: solo se pueden conectar sus datos si ofrece API/exportación o permiso de uso.

## Límites de esta versión
- El modelo de goles es orientativo y no está calibrado ni validado para apuestas.
- Córneres y tarjetas aún no tienen modelos predictivos dedicados; se pueden importar datos CSV, pero no se deben presentar como predicciones hasta implementar esos modelos.
- El historial SQLite puede perderse o no persistir en ciertos alojamientos gratuitos que reinician el almacenamiento. Para mantenerlo de forma fiable hace falta almacenamiento persistente externo.
- La actualización automática 24/7 requiere un servicio de tareas programadas y una fuente con cobertura adecuada. Esta versión consulta datos cuando se usa y utiliza caché.
- El modelo no garantiza resultados ni rentabilidad.
