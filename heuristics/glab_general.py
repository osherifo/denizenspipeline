"""
General heuristic file to convert raw MRI data for GLAB experiments
to BIDS format.

See (https://heudiconv.readthedocs.io/en/latest/heuristics.html) for
more information about the components of a heuristics file.
See (https://github.com/gallantlab/mvdocprep?tab=readme-ov-file) for
more examples of heuristics files.

This file has been used for the following GLAB experiments:
    - shortfilms
    - psychedelicVM

20241009 : added condition parsing for functional scans
20241104 : updated to have convert_mri_to_bids pass in subject + session
"""
import re
from collections import defaultdict

# specify options to populate the 'IntendedFor' field in the BIDS JSON file
POPULATE_INTENDED_FOR_OPTS = {
    #'matching_parameters': ['ImagingVolume', 'Shims'],
    'matching_parameters': ['Shims'],
    'criterion': 'Closest'
}
# series IDs for fieldmaps may start with the following strings
FMAPS = ["fmap", "iso_topup", "iso_gre", "gre_field_mapping"]
# series IDs for functionals may start with the following strings
stories = [
    "howtodraw", "life", "myfirstdaywiththeyankees", "naked", "undertheinfluence", "wheretheressmoke",
    "legacy", "alternateithicatom", "avatar", "odetostepfather", "souls", 
]
FUNCS = ["func", "mb3", "iso_ep2d_neuro", "iso_mb3"] + stories
# the number of instances per run for different series_IDs
N_FMAPS = {
    "iso_topup_se_WEseq": 2, # 2 fmaps
    "iso_topup_mb3": 2, # 2 fmaps
    "iso_gre_field_mapping": 2, # 3 fmaps
    "gre_field_mapping": 2
}
N_FUNCS = {
    "mb3_production": 2, # 1 functionals + 1 SBRef
    "iso_ep2d_neuro_Base20120312": 1, # 1 functional,
    "iso_mb3_tqa": 2, # 1 functional + 1 SBRef
}
story_n = {s:1 for s in stories}
N_FUNCS.update(story_n)

###########################################################
## FUNCTIONS TO CHECK THE TYPE OF SCAN COLLECTED
###########################################################

def _is_anat(seq) -> bool:
    """Returns True if sequence is an anatomical scan.
    
    Assumes the series description starts with 'anat-T1w'.
    """
    # omar: added 'memprage' to the anatomical scans
    return seq.series_description.startswith("anat-T1w") or seq.series_description.lower().startswith("memprage")

def _is_fmap(seq) -> bool:
    """Returns True if sequence is a fieldmap, and is not
    a single-band reference.

    Assumes the series description starts with 'fmap', and
    does not contain 'sbref'.
    """
    sd = seq.series_description.lower()
    sbref = _is_sbref(seq)
    return any([sd.startswith(fmap) for fmap in FMAPS]) and not sbref

def _is_func(seq) -> bool:
    """Returns True if sequence is a functional scan, and is not
    the phase image.

    Assumes the series description starts with 'func', and the
    image type does not contain 'P'.
    """
    sd = seq.series_description.lower()
    phase = "P" in seq.image_type
    return any([sd.startswith(func) for func in FUNCS]) and not phase

def _is_sbref(seq) -> bool:
    """Returns True if sequence is a single-band reference."""
    return "sbref" in seq.series_description.lower()

###########################################################
## FUNCTIONS TO GET CERTAIN INFO FROM THE SERIES DESCRIPTION
###########################################################

def _parse_session(series_description:str) -> str:
    """Parse the session from the series description.
    
    Assumes that the session information follows the format:
        ses-<session_label>
    """
    ses = None
    p = re.compile(r"ses-([a-zA-Z0-9]*)")
    m = p.search(series_description)
    if m:
        ses = m.groups()[0]
    return ses

def _parse_run(series_description:str) -> int:
    """Parse the run number from the series description.

    Assumes that the run information follows the format:
        run-<run_number>
    """
    run = None
    p = re.compile(r"run-([0-9]*)")
    m = p.search(series_description)
    if m:
        run = int(m.groups()[0])
    return run

def _parse_acquisition(series_description:str) -> str:
    """Parse the acquisition label from the series description.

    Assumes that the acquisition information follows the format:
        acq-<acquisition_label>
    """
    acq = None
    p = re.compile(r"acq-([a-zA-Z]*)")
    m = p.search(series_description)
    if m:
        acq = m.groups()[0].lower()
    return acq

def _parse_reconstruction(image_type:str) -> str:
    """Parse the reconstruction label from the series description.

    Assumes that the reconstruction information follows the format:
        rec-<reconstruction_label>
    """
    rec = None
    if "MEAN" in image_type:
        # for anatomical scans
        rec = "rms"
    elif "NORM" in image_type:
        # for functional scans
        rec = "norm"
    return rec

def _parse_part(image_type:str) -> str:
    """Parse the part of the MRI data (magnitude, phase) from the series 
    description.
    
    Assume that the part information follows the format:
        part-<label>
    """
    if "M" in image_type:
        return "mag"
    elif "P" in image_type:
        return "phase"
    else:
        return None

def _parse_direction(series_description:str) -> str:
    """Parse the phase encoding direction from the series description.
    Used for fieldmap scans.
    """
    if "_pa" in series_description.lower():
        return "PA"
    elif "_ap" in series_description.lower():
        return "AP"
    else:
        return None

def _parse_task(series_description:str) -> str:
    """Parse the task label from the series description.
    Used for functional scans.

    Assumes that the task information follows the format:
        task-<task_label>
    """
    p = re.compile(r"task-([a-zA-Z0-9]*)")
    m = p.search(series_description)
    if m is None:
        return None
    task = m.groups()[0]

    # fix task labels for runs in specific experiments
    session = _parse_session(series_description)

    # for the shortfilms experiment
    if "shortfilms" in session:
        if task == "test":
            # add the session number to the task label
            session_num = re.findall(r'\d+', session)[0]
            task += session_num
        elif "train" in task:
            # change the run number to reflect both the session
            # and the run number
            session_num = int(re.findall(r'\d+', session)[0])
            task_num = int(re.findall(r'\d+', task)[0])
            session_run_num = ((session_num - 1) * 4) + task_num
            task = "train" + str(session_run_num).zfill(2)

    return task

def _parse_cond(series_description:str) -> str:
    """Parse the condition label from the series description.
    Used for functional scans.

    Assumes that the condition information follows the format:
        cond-<condition_label>
    """
    p = re.compile(r"cond-([a-zA-Z0-9]*)")
    m = p.search(series_description)
    if m is None:
        return None
    return m.groups()[0]

def _match_story(series_description:str) -> str:
    """Return the story name if the series description starts with a known
    story, otherwise return None."""
    sd = series_description.lower()
    for story in stories:
        if sd.startswith(story):
            return story
    return None

###########################################################
## FUNCTIONS TO BUILD BIDS DIRECTORY STRUCTURE
###########################################################

def _build(
        scan:str,
        session:str=None,
    ) -> str:
    """Build the base BIDS directory structure:

    sub-<subject>/<scan>/sub-<subject>_ses-<session>

    Parameters
    ----------
    scan : str ('anat'|'func'|'fmap')
        The type of scan.
    acquisition : str
        The acquisition label (e.g., 'rms')
    reconstruction : str
        The reconstruction label (e.g., 'norm')
    """
    if scan not in ["anat", "func", "fmap"]:
        raise ValueError("scan must be ['anat' | 'func' | 'fmap']")
    basedir = "sub-{subject}/{session}"
    scan += "/sub-{subject}_{session}"
    return f"{basedir}/{scan}"

def build_anat(
        run_nr:int=None,
        session:str=None,
        acquisition:str=None,
        reconstruction:str=None
    ) -> str:
    """Build the BIDS directory structure for an anatomical scan:
    
    sub-<subject>/anat/sub-<subject>_ses-<session>_run-<run_nr>_T1w

    Parameters
    ----------
    run_nr : int
        The run number of the scan. Only necessary if there are
        multiple of the same anatomical scan.
    """
    # omar: remove aquision and reconstruction parameters of _build
    # since the function does not take them
    anat = _build("anat", session)
    if run_nr is not None:
        anat += f"_run-{run_nr:02d}"
    anat += "_T1w"
    return anat

def build_fmap(
        direction:str,
        run_nr:int=None,
        session:str=None,
        acquisition:str=None,
        im_type:str=None
    ) -> str:
    """Build the BIDS directory structure for a fieldmap scan:

    sub-<label>[_ses-<label>][_acq-<label>]_dir-<label>[_run-<index>][_<im_type> | _epi].nii[.gz]

    Parameters
    ----------
    direction : str ('AP'|'PA')
        The phase encoding direction of the scan.
    run_nr : int
        The run number of the scan. Only necessary if the
        subject has multiple anatomical scans.
    """
    fmap = _build("fmap", session)
    if acquisition is not None:
        fmap += f"_acq-{acquisition}"
    if direction is not None:
        fmap += f"_dir-{direction}"
    if run_nr is not None:
        fmap += f"_run-{run_nr:02d}"

    if im_type is not None:
        fmap += f"_{im_type}"
    else:
        fmap += "_epi"
    return fmap

def build_func(
        task:str,
        cond:str=None,
        run_nr:int=None,
        sbref:bool=False,
        session:str=None,
        acquisition:str=None,
        reconstruction:str=None,
    ) -> str:
    """Build the BIDS directory structure for a functional scan:

    sub-<label>[_ses-<label>]_task-<label>[_acq-<label>][_rec-<label>][_run-<index>]_[bold|sbref].nii[.gz]

    Parameters
    ----------
    task : str
        The task label of the scan.
    cond : str
        The condition label of the scan.
    run_nr : int
        The run number of the scan. Only necessary if there are
        multiple of the same functional scan.
    sbref : bool
        True if the scan is a single-band reference.
    """
    func = _build("func", session)
    func += f"_task-{task}"
    if cond is not None:
        func += f"{cond}"
    if acquisition is not None:
        func += f"_acq-{acquisition}"
    if reconstruction is not None:
        func += f"_rec-{reconstruction}"
    if run_nr is not None:
        func += f"_run-{run_nr:02d}"
    func += "_bold" if not sbref else "_sbref"
    return func

###########################################################
## OTHER HELPER FUNCTIONS
###########################################################

def _create_key(template, outtype=("nii.gz",), annotation_classes=None):
    """Create the conversion key in infotodict."""
    if template is None or not template:
        raise ValueError("Template must be a valid format string")
    return template, outtype, annotation_classes

def _fix_duplicates(info_dict) -> dict:
    """Fix duplicates by removing all but the last duplicated run."""
    fixed_info_dict = dict()
    for key, value in info_dict.items():
        if len(value) == 1:
            fixed_info_dict[key] = value
        else:
            # remove all but the last duplicated run
            fixed_info_dict[key] = [value[-1]]
    return fixed_info_dict

def _get_series_match(series_desc:str, param_dict:dict) -> str:
    """Return value of dict with best matching key."""
    # default for fieldmaps is 2, default for functionals is 1
    val = 1 if any([series_desc.startswith(func) for func in FUNCS]) \
        else 2
    nmatches = 0
    for key_, val_ in param_dict.items():
        if key_ in series_desc:
            val = val_
            nmatches += 1
    if nmatches > 1:
        raise ValueError(
            f"Series description ({series_desc}) is ambiguous ",
            "-- matches multiple keys in the param_dictionary provided.")
    return val

###########################################################
## MAIN HEUDICONV FUNCTIONS
###########################################################
"""
This function does most of the work in the heuristic file. It takes a list of
SeqInfo objects and returns a dictionary that maps the template to the series
ID. The template is a string that describes the BIDS filename structure. The
series ID is the DICOM series ID.

An example SeqInfo object (for the SBRef image of the A-P fieldmap):
    SeqInfo(
        total_files_till_now=1,
        example_dcm_file='IM-0005-0001.dcm',
        series_id='7-fmap_ses-shortfilms01_dir-AP_run-01',
        dcm_dir_name='fmap_ses-shortfilms01_dir-AP_run-01_SBRef_7',
        series_files=1,
        unspecified='',
        dim1=84, dim2=84, dim3=56, dim4=1,
        TR=-1.0, TE=-1.0,
        protocol_name='fmap_ses-shortfilms01_dir-AP_run-01',
        is_motion_corrected=False,
        is_derived=False,
        patient_id='20240604MW',
        study_description='GALLANT LAB SHARED',
        referring_physician_name='',
        series_description='fmap_ses-shortfilms01_dir-AP_run-01_SBRef',
        sequence_name='',
        image_type=('ORIGINAL', 'PRIMARY', 'FMRI', 'NONE'),
        accession_number='',
        patient_age='0XXY',
        patient_sex='X',
        date=None,
        series_uid='1.3.12.2.1107.5.2.43.166319.2024060412151955044524669.0.0.0',
        time=None,
        custom=None
    )
"""

def infotodict(seqinfo:list) -> dict:
    """Heuristic evaluator for determining which runs belong where.

    Template fields - follow python string module:
        item: index within category
        subject: participant id
        seqitem: run number during scanning
        subindex: sub index within group

    Returns
    -------
    info : dict
        Mapping from sequence information to file structure.
    """
    print("\n**********************************************")
    print("**************** INFO TO DICT ****************")
    print("**********************************************")
    info = defaultdict(list)
    
    # track the number of series directories per "run" of fieldmap
    # or functional data collected
    fmap_nr = 1 # the fieldmap run number
    fmap_count = 0 # when == N_FMAPS[<series>], increase fmap_nr
    func_nr = 1 # the functional run number
    func_count = 0 # when == N_FUNCS[<series>], increase func_nr

    # sort seqinfo by the instance number (order of acquisition)
    instance_nrs = [int(s.series_id.split("-")[0]) for s in seqinfo]
    seqinfo = [s for _, s in sorted(zip(instance_nrs, seqinfo))]
    for s in seqinfo:
        # the template is set for each sequence, according to the
        # type of data that is collected
        template = ""
        # set the default acquisition
        acquisition = None
        
        # the series description is the name of the sequence
        # (e.g., 'func_ses-shortfilms01_task-train01')
        series_desc = s.series_description
        # the image type is a tuple of the DICOM image type
        # (e.g., ('ORIGINAL', 'PRIMARY', 'FMRI', 'NONE'))
        image_type = s.image_type

        print(s.series_id)
        
        # check if sequence collects an ANATOMICAL scan
        if _is_anat(s):
            session = _parse_session(series_desc)
            acquisition = _parse_acquisition(series_desc)
            reconstruction = _parse_reconstruction(image_type)

            run_nr = _parse_run(series_desc)
            print(f" ANATOMICAL: session={session}, acquisition={acquisition}")

            template = build_anat(
                run_nr=run_nr,
                session=session,
                acquisition=acquisition,
                reconstruction=reconstruction
            )
        
        # check if sequence collects a FIELDMAP scan
        elif _is_fmap(s):
            session = _parse_session(series_desc)
            reconstruction = _parse_reconstruction(image_type)

            direction = _parse_direction(series_desc)
            run_nr = _parse_run(series_desc)
            if run_nr is None:
                # infer the run number
                run_nr = fmap_nr
                print("run_nr:", run_nr)
                fmap_count += 1
                print("fmap_count:", fmap_count)
                if fmap_count == _get_series_match(series_desc, N_FMAPS):
                    fmap_nr += 1
                    fmap_count = 0

            part = _parse_part(image_type)
            im_type = None
            if (part=="mag") and ("gre" in series_desc):
                im_type = "magnitude"
            if (part=="phase") and ("gre" in series_desc):
                im_type = "phasediff"
                
            print(f" FIELDMAP: session={session}, direction={direction}, run={run_nr}, part={part}")

            template = build_fmap(
                direction=direction,
                run_nr=run_nr,
                session=session,
                acquisition=acquisition,
                im_type=im_type
            )
        
        # check if sequence collects a FUNCTIONAL scan
        elif _is_func(s):
            session = _parse_session(series_desc)
            acquisition = _parse_acquisition(series_desc)
            reconstruction = _parse_reconstruction(image_type)
            
            task = _parse_task(series_desc)
            run_nr = _parse_run(series_desc)
            if task is None:
                # check if series description starts with a known story name
                story_match = _match_story(series_desc)
                if story_match:
                    task = story_match
                    # stories are single-run, no run number needed
                    run_nr = None
                else:
                    if run_nr is None:
                        run_nr = func_nr
                    # default to train<RunNum> (e.g., train01)
                    task = f"train{str(func_nr).zfill(2)}"
                func_count += 1
                if func_count == _get_series_match(series_desc, N_FUNCS):
                    func_nr += 1
                    func_count = 0

            cond = _parse_cond(series_desc)      
            sbref = _is_sbref(s)
            print(f" FUNCTIONAL: session={session}, task={task}, run={run_nr}")
            
            template = build_func(
                task=task,
                cond=cond,
                run_nr=run_nr,
                sbref=sbref,
                session=session,
                reconstruction=reconstruction,
                acquisition=acquisition,
            )
        
        # add the template to the info dictionary
        if template:
            print(f" {template} <-- {s.series_id}\n")
            info[_create_key(template)].append(s.series_id)
    
    print("**********************************************\n")
    info = _fix_duplicates(info)
    return dict(info)
