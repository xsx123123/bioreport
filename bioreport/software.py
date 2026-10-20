"""Software versions embedded in configuration, with a legacy file fallback."""
def software_records(config):
    import pandas as pd
    if 'software_versions' in config:
        frame = pd.DataFrame(config['software_versions'])
    else:
        from bioreport.utils.visualize_utils import load_software_data
        path = config.get('input_files', {}).get('software_versions_file')
        if not path:
            raise ValueError('Provide software_versions or input_files.software_versions_file')
        frame = load_software_data(str(path))
    if frame.empty or not {'Software', 'Version'} <= set(frame):
        raise ValueError('Software versions must contain nonempty Software/Version records')
    for key in ('Software', 'Version'):
        if frame[key].isna().any() or frame[key].astype(str).str.strip().eq('').any():
            raise ValueError(f'Software versions contain an empty {key}')
        frame[key] = frame[key].astype(str)
    if frame['Software'].str.casefold().duplicated().any():
        raise ValueError('Software versions contain duplicate software names')
    return frame


def software_source(config):
    return ((config.get('_config_path', '') + '#software_versions') if 'software_versions' in config
            else config.get('input_files', {}).get('software_versions_file', ''))
