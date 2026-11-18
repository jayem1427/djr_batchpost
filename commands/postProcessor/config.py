from ...config import ADDIN_NAME, COMPANY_NAME

#
# Configuration for the djr_batchpost add-in.
# Global variables shared across the post-processing command.
#

SETTINGS_VERSION = 8

#palettes
POST_PROCESSOR_PALETTE_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_post_processor_palette_id'

CMD_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_postProcessorDialog'
CMD_NAME = 'DJR Batch Post'
CMD_DESCRIPTION = 'Batch post-process Fusion CAM operations into one or more G-code files, with optional rapid restoration, multi-setup merge, and A-axis rotation.'

# One-click combined post (no dialog)
QUICK_CMD_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_postCombined'
QUICK_CMD_NAME = 'Post Combined'
QUICK_CMD_DESCRIPTION = ('One click: post every operation in the selected setups (or all setups) into one combined G-code file, '
                         'using the NC Program, output folder and options last used in DJR Batch Post.')
