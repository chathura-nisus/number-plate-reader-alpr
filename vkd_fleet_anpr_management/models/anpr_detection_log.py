from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ANPRDetectionLog(models.Model):
    _name = 'anpr.detection.log'
    _description = 'ANPR Detection Log'
    _order = 'detection_time desc'
    _rec_name = 'license_plate'

    # Core fields for logging
    license_plate = fields.Char(
        string='License Plate',
        required=True,
        index=True,
        help='Detected license plate number'
    )

    detection_time = fields.Datetime(
        string='Detection Time',
        required=True,
        default=fields.Datetime.now,
        help='When the license plate was detected'
    )

    confidence_score = fields.Float(
        string='Confidence Score',
        help='OCR confidence score for the detection'
    )

    camera_source_identifier = fields.Char(
        string='Camera Source Identifier',
        help='Identifier for the source camera (e.g., IP address, device ID from Flask app)'
    )

    location_id = fields.Many2one(
        'anpr.camera.location',
        string='Location',
        index=True,
        ondelete='restrict',
        help='Physical location of the camera that made the detection.'
    )

    # MODIFIED: Simplified binary fields. Odoo now handles attachment creation automatically.
    captured_image = fields.Binary(
        string='Plate Image',
        attachment=True,
        help='The captured license plate image (cropped). Stored as an attachment.'
    )

    full_frame_image = fields.Binary(
        string='Full Frame Snapshot',
        attachment=True,
        help='The full camera frame snapshot at the time of detection. Stored as an attachment.'
    )

    # Kept this useful field for filtering and grouping
    detection_date = fields.Date(
        string='Detection Date',
        compute='_compute_detection_date',
        store=True,
        index=True
    )

    @api.depends('detection_time')
    def _compute_detection_date(self):
        """Computes the date part from the detection timestamp for easier filtering."""
        for record in self:
            if record.detection_time:
                record.detection_date = record.detection_time.date()
            else:
                record.detection_date = False

    @api.model_create_multi
    def create(self, vals_list):
        """
        Overrides the create method to dynamically handle camera locations sent from the ANPR server.
        If a 'location' name is passed instead of an ID, this method will find the corresponding
        record or create a new one.
        """
        processed_vals_list = []
        # Find or create location records in a batch to be efficient
        location_names_to_find = {
            vals.get('location') for vals in vals_list
            if 'location' in vals and isinstance(vals.get('location'), str) and 'location_id' not in vals
        }

        location_map = {}
        if location_names_to_find:
            Location = self.env['anpr.camera.location']
            existing_locations = Location.search([('name', 'in', list(location_names_to_find))])
            for loc in existing_locations:
                location_map[loc.name] = loc.id

            # Determine which locations are new and create them
            new_location_names = location_names_to_find - set(location_map.keys())
            if new_location_names:
                new_locations_vals = [{'name': name} for name in new_location_names]
                try:
                    new_records = Location.create(new_locations_vals)
                    for rec in new_records:
                        location_map[rec.name] = rec.id
                    _logger.info(f"Auto-created {len(new_records)} new camera location(s).")
                except Exception as e:
                    _logger.error(f"Failed to auto-create new camera locations: {e}")

        for vals in vals_list:
            # If a location string was passed, map it to its ID
            location_name = vals.get('location')
            if location_name and isinstance(location_name, str):
                vals.pop('location')  # Remove the temporary key
                location_id = location_map.get(location_name)
                if location_id:
                    vals['location_id'] = location_id

            # Handle camera_source field mapping from Flask integration
            if 'camera_source' in vals and 'camera_source_identifier' not in vals:
                vals['camera_source_identifier'] = vals.pop('camera_source')

            processed_vals_list.append(vals)

        new_logs = super().create(processed_vals_list)
        _logger.info(f"Created {len(new_logs)} new ANPR log(s).")
        return new_logs
