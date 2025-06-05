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
        default=fields.Datetime.now,  # Good default if not provided
        help='When the license plate was detected'
    )

    confidence_score = fields.Float(
        string='Confidence Score',
        help='OCR confidence score for the detection'
    )

    camera_source_identifier = fields.Char(  # Renamed from camera_source for clarity
        string='Camera Source Identifier',
        help='Identifier for the source camera (e.g., IP address, device ID from Flask app)'
    )

    location_id = fields.Many2one(  # Changed from Char to Many2one
        'anpr.camera.location',
        string='Location',
        index=True,
        ondelete='restrict',  # Or 'set null' if you prefer to keep logs if location is deleted
        help='Physical location of the camera that made the detection.'
    )

    # Plate ROI (cropped image)
    image_filename = fields.Char(
        string='Plate Image Filename',
        help='Original filename of the captured plate image'
    )

    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Plate Image Attachment',
        help='Link to the stored plate image attachment (cropped plate)'
    )

    captured_image = fields.Binary(
        string='Captured Plate Image',
        attachment=True,  # Odoo handles ir.attachment creation for this field's data
        help='The captured license plate image (cropped)',
        related='attachment_id.datas',
        readonly=False
    )

    # Full Frame Snapshot
    full_frame_filename = fields.Char(
        string='Full Frame Filename',
        help='Filename of the full camera frame snapshot'
    )

    full_frame_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Full Frame Attachment',
        help='Link to the stored full frame snapshot attachment'
    )

    full_frame_image = fields.Binary(
        string='Full Frame Snapshot',
        attachment=True,  # Odoo handles ir.attachment creation for this field's data
        help='The full camera frame snapshot at the time of detection',
        related='full_frame_attachment_id.datas',
        readonly=False
    )

    detection_date = fields.Date(
        string='Detection Date',
        compute='_compute_detection_date',
        store=True,
        index=True
    )

    @api.depends('detection_time')
    def _compute_detection_date(self):
        for record in self:
            if record.detection_time:
                record.detection_date = record.detection_time.date()
            else:
                record.detection_date = False

    @api.model
    def create(self, vals):
        """
        Override create to handle location string from Flask and find/create
        the corresponding anpr.camera.location record.
        Also handles setting the filenames if provided directly with binary data.
        The Flask app is now designed to create the log, then attachments, then link them.
        This create method will primarily handle the location_id lookup if 'location' (string) is passed.
        Binary data for 'captured_image' and 'full_frame_image' passed here will have attachments
        auto-created by Odoo due to `attachment=True`. The Flask app's explicit attachment creation
        and linking via `attachment_id` and `full_frame_attachment_id` will take precedence if done after this create.
        """

        # Handle location string if passed (e.g., from an external system not knowing location_id)
        # The current Flask app sends 'location' as a string in odoo_data, which becomes 'location' in vals.
        # We need to map this to location_id.
        if 'location' in vals and isinstance(vals['location'], str) and 'location_id' not in vals:
            location_name = vals.pop('location')
            if location_name:
                Location = self.env['anpr.camera.location']
                location_record = Location.search([('name', '=ilike', location_name)], limit=1)
                if not location_record:
                    try:
                        location_record = Location.create({'name': location_name})
                        _logger.info(f"Created new camera location: '{location_name}' with ID {location_record.id}")
                    except Exception as e:
                        _logger.error(f"Failed to create new camera location '{location_name}': {e}")
                        # Decide how to handle: raise error, or proceed without location?
                        # For now, proceed without, or raise UserError.
                        # raise UserError(_("Could not create new camera location: %s") % location_name)
                if location_record:
                    vals['location_id'] = location_record.id

        # If binary data is passed directly for 'captured_image' or 'full_frame_image',
        # Odoo's `attachment=True` will create ir.attachment records.
        # The `related` field should then automatically populate `attachment_id` and `full_frame_attachment_id`.
        # However, the Flask app's current logic is to create the log *without* binary data,
        # then create attachments separately, and then *write* the attachment IDs.
        # So, this part of the create method is more for direct Odoo UI/method calls.

        if 'captured_image' in vals and vals['captured_image'] and not vals.get('image_filename'):
            vals[
                'image_filename'] = f"plate_{vals.get('license_plate', 'unknown')}_{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"

        if 'full_frame_image' in vals and vals['full_frame_image'] and not vals.get('full_frame_filename'):
            vals[
                'full_frame_filename'] = f"fullframe_{vals.get('license_plate', 'unknown')}_{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"

        # Rename camera_source from Flask to camera_source_identifier if it comes in as 'camera_source'
        if 'camera_source' in vals and 'camera_source_identifier' not in vals:
            vals['camera_source_identifier'] = vals.pop('camera_source')

        new_log = super(ANPRDetectionLog, self).create(vals)
        _logger.info(
            f"ANPR Log created with ID: {new_log.id}. Location ID: {new_log.location_id.id if new_log.location_id else 'None'}")
        _logger.info(
            f"Log details - Plate Attach ID: {new_log.attachment_id.id if new_log.attachment_id else 'N/A'}, Full Frame Attach ID: {new_log.full_frame_attachment_id.id if new_log.full_frame_attachment_id else 'N/A'}")

        return new_log

    # If you want to ensure filenames are set when attachments are linked via attachment_id fields:
    # @api.onchange('attachment_id')
    # def _onchange_attachment_id(self):
    #     if self.attachment_id and not self.image_filename:
    #         self.image_filename = self.attachment_id.name

    # @api.onchange('full_frame_attachment_id')
    # def _onchange_full_frame_attachment_id(self):
    #     if self.full_frame_attachment_id and not self.full_frame_filename:
    #         self.full_frame_filename = self.full_frame_attachment_id.name
