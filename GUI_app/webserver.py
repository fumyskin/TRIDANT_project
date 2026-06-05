import ssl
import http.server
import socketserver  # 💡 Added for threading support

PORT = 8443

# 💡 Use ThreadingTCPServer instead of HTTPServer to handle concurrent browser requests
class ThreadedHTTP2Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True  # Prevents "Address already in use" errors on restart

# Set up the standard request handler
handler = http.server.SimpleHTTPRequestHandler

# Initialize the server on all interfaces (0.0.0.0)
server = ThreadedHTTP2Server(('0.0.0.0', PORT), handler)

# Configure the SSL Context
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain('cert.pem', 'key.pem')

# Wrap the server socket with SSL
server.socket = ctx.wrap_socket(server.socket, server_side=True)

print(f"🚀 Threaded HTTPS server running!")
print(f"👉 Open your browser to: https://localhost:{PORT}")
print("Press Ctrl+C to stop.")

try:
    server.serve_forever()
except KeyboardInterrupt:
    print("\nShutting down server.")
    server.server_close()