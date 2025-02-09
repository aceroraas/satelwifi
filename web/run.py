import os
import sys
from pathlib import Path

# Añadir el directorio raíz al path para importar los módulos existentes
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))

from backend.app import app

if __name__ == '__main__':
    # Change to the script's directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Determinar el modo de ejecución
    if os.getenv('FLASK_ENV') == 'development':
        # Modo desarrollo - usar servidor Flask
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=True
        )
    else:
        # Modo producción - usar Gunicorn
        import gunicorn.app.base

        class StandaloneApplication(gunicorn.app.base.BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()

            def load_config(self):
                for key, value in self.options.items():
                    self.cfg.set(key.lower(), value)

            def load(self):
                return self.application

        options = {
            'bind': '0.0.0.0:5000',
            'workers': 3,  # (2 x num_cores) + 1
            'worker_class': 'sync',
            'timeout': 120,
            'accesslog': str(root_dir / 'satelwifi.log'),
            'errorlog': str(root_dir / 'satelwifi.log'),
            'capture_output': True,
            'loglevel': 'info'
        }

        StandaloneApplication(app, options).run()
