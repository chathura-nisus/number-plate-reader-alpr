from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import requests
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

try:
    import jwt
except ImportError:
    _logger.critical(
        "The PyJWT library is not installed in Odoo's environment. API calls will fail. Please run 'pip install PyJWT'.")
    jwt = None


class ANPRCameraLocation(models.Model):
    _name = 'anpr.camera.location'
    _description = 'ANPR Camera Location'
    # MODIFIED: Added mail.thread to correctly enable tracking
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(string='Location Name', required=True, index=True)
    description = fields.Text(string='Description')
    source = fields.Char(string='Camera Source', help="e.g., 0, 1, or an rtsp:// stream URL")

    # MODIFIED: Replaced `tracking=True` with the new syntax `tracking=1`
    state = fields.Selection([
        ('stopped', 'Stopped'),
        ('starting', 'Starting...'),
        ('running', 'Running'),
        ('stopping', 'Stopping...'),
        ('error', 'Error')
    ], string='Status', default='stopped', readonly=True, copy=False, tracking=1)

    state_message = fields.Text(string="State Message", readonly=True)

    # ... the rest of the file remains the same ...
    def _generate_jwt_token(self):
        self.ensure_one()
        if not jwt:
            raise UserError(
                _("The 'PyJWT' library is not installed on the Odoo server. Please contact your administrator."))
        get_param = self.env['ir.config_parameter'].sudo().get_param
        secret_key = get_param('anpr.jwt_secret_key')
        if not secret_key:
            raise UserError(_("The ANPR API Secret Key is not configured in settings."))
        payload = {'iat': datetime.utcnow(), 'exp': datetime.utcnow() + timedelta(seconds=60),
                   'iss': 'odoo_anpr_module', 'user_id': self.env.user.id}
        token = jwt.encode(payload, secret_key, algorithm="HS256")
        return token

    def _get_api_headers(self):
        return {'Authorization': f'Bearer {self._generate_jwt_token()}', 'Content-Type': 'application/json'}

    @api.model
    def _get_flask_server_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('anpr.flask_server_url')
        if not base_url:
            raise UserError(_("The ANPR Flask Server URL is not configured in settings."))
        return base_url.rstrip('/')

    def action_start_stream(self):
        self.ensure_one()
        flask_url = self._get_flask_server_url()
        endpoint = f"{flask_url}/api/start_camera"
        payload = {'location_id': self.id, 'name': self.name, 'source': self.source}
        try:
            self.write({'state': 'starting', 'state_message': 'Sending start command...'})
            response = requests.post(endpoint, json=payload, headers=self._get_api_headers(), timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            error_message = f"Failed to send start command: {e}"
            _logger.error("Could not send start command for location %s. Error: %s", self.name, e)
            self.write({'state': 'error', 'state_message': error_message})
        except Exception as e:
            self.write({'state': 'error', 'state_message': str(e)})

    def action_stop_stream(self):
        self.ensure_one()
        flask_url = self._get_flask_server_url()
        endpoint = f"{flask_url}/api/stop_camera"
        cam_id = f"cam_{self.id}"
        payload = {'id': cam_id}
        try:
            self.write({'state': 'stopping', 'state_message': 'Sending stop command...'})
            response = requests.post(endpoint, json=payload, headers=self._get_api_headers(), timeout=10)
            response.raise_for_status()
            self.write({'state': 'stopped', 'state_message': 'Stop command sent successfully.'})
        except requests.exceptions.RequestException as e:
            error_message = f"Failed to send stop command: {e}"
            _logger.error("Could not send stop command for location %s. Error: %s", self.name, e)
            self.write({'state': 'error', 'state_message': error_message})
        except Exception as e:
            self.write({'state': 'error', 'state_message': str(e)})
