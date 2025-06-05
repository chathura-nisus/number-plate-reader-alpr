from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ANPRCameraLocation(models.Model):
    _name = 'anpr.camera.location'
    _description = 'ANPR Camera Location'
    _order = 'name'

    name = fields.Char(
        string='Location Name',
        required=True,
        index=True,
        help="Descriptive name for the camera location (e.g., Main Gate, North Entrance)."
    )
    description = fields.Text(string='Description')

    # For future use, e.g., linking to specific camera hardware records
    # camera_device_id = fields.Many2one('anpr.camera.device', string='Camera Device')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "A camera location with this name already exists!")
    ]

    # You might want a display_name that includes more info if needed
    # def name_get(self):
    #     result = []
    #     for record in self:
    #         name = record.name
    #         # if record.description:
    #         #     name = f"{name} ({record.description[:20]}...)"
    #         result.append((record.id, name))
    #     return result
