import os
import sys

# Añadir el directorio raíz al path para importar los módulos existentes
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import app

if __name__ == '__main__':
    # Change to the script's directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Run Flask application on all interfaces
    app.run(debug=True, host='0.0.0.0', port=5000)
