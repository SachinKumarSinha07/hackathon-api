"""VAPT Import Controller - API endpoints for VAPT Excel import"""

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, status
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.api.schemas.vapt_import_schema import VAPTImportResponse
from app.api.services.vapt_import_service import VAPTImportService
from app.core.logger import get_logger
from app.api.middleware.error_handler import APIException

logger = get_logger(__name__)

router = APIRouter(prefix="/vapt", tags=["VAPT Import"])


@router.post(
    "/import",
    response_model=VAPTImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import VAPT Excel Report",
    description="""
    Import a VAPT (Vulnerability Assessment and Penetration Testing) Excel report.
    
    **Process:**
    1. Upload Excel file to S3
    2. Extract vulnerability data and POC images from Excel
    3. Upload all POC images to S3
    4. Link images to their respective vulnerabilities
    5. Save all vulnerabilities to the database
    
    **Excel Format:**
    The Excel file must contain two sheets:
    - "Detailed Vulnerability Report": Contains vulnerability information (11 columns)
    - "POCs": Contains proof-of-concept images
    
    **Required Fields:**
    - Excel file (.xlsx format)
    - Project ID (existing project)
    - Created By (user ID)
    - Round ID (required - import must be associated with a round)
    
    **Returns:**
    - Summary of imported data
    - List of created vulnerabilities with their IDs
    - S3 URLs for Excel file and POC images
    """
)
async def import_vapt_excel(
    file: UploadFile = File(..., description="VAPT Excel file (.xlsx)"),
    project_id: int = Form(..., description="Project ID to associate vulnerabilities", gt=0),
    created_by: int = Form(..., description="User ID who is importing the data", gt=0),
    round_id: int = Form(..., description="Round ID for the VAPT assessment (required)", gt=0),
    db: Session = Depends(get_db),
):
    """
    Import VAPT Excel report and process vulnerabilities.
    
    Args:
        file: Uploaded Excel file
        project_id: ID of the project
        created_by: ID of the user performing the import
        round_id: Round ID (required)
        db: Database session
        
    Returns:
        VAPTImportResponse: Import results with summary and vulnerability list
    """
    # Validate file type
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise APIException(
            status_code=400,
            message="Invalid file type. Only Excel files (.xlsx, .xls) are supported.",
            message_key="vapt.import.invalid_file_type"
        )
    
    logger.info(
        f"VAPT import requested: file={file.filename}, project_id={project_id}, "
        f"created_by={created_by}, round_id={round_id}"
    )
    
    try:
        # Initialize service
        service = VAPTImportService(db)
        
        # Process the import
        result = await service.import_vapt_excel(
            excel_file=file.file,
            filename=file.filename,
            project_id=project_id,
            created_by=created_by,
            round_id=round_id,
        )
        
        logger.info(f"VAPT import completed successfully for file: {file.filename}")
        return result
        
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during VAPT import: {str(e)}", exc_info=True)
        raise APIException(
            status_code=500,
            message=f"An unexpected error occurred during import: {str(e)}",
            message_key="vapt.import.unexpected_error"
        )


@router.get(
    "/vulnerabilities",
    response_model=VAPTImportResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve vulnerabilities",
    description="""
    Retrieve vulnerabilities filtered by project, round, severity and status.

    All filters are optional and combined with AND logic. Any filter left empty
    is ignored. The response shape matches the VAPT import response.

    **Query Parameters:**
    - `project_id`: Optional - Filter by project ID
    - `round_id`: Optional - Filter by round ID
    - `severity`: Optional - Filter by severity (case-insensitive)
    - `status`: Optional - Filter by status (case-insensitive)
    """
)
def get_vulnerabilities(
    project_id: Optional[int] = Query(None, description="Filter by project ID", gt=0),
    round_id: Optional[int] = Query(None, description="Filter by round ID", gt=0),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    """
    Retrieve vulnerabilities based on the provided filters.

    Args:
        project_id: Optional project ID filter
        round_id: Optional round ID filter
        severity: Optional severity filter
        status: Optional status filter
        db: Database session

    Returns:
        VAPTImportResponse: Matching vulnerabilities
    """
    logger.info(
        f"Retrieving vulnerabilities: project_id={project_id}, round_id={round_id}, "
        f"severity={severity}, status={status}"
    )

    service = VAPTImportService(db)
    return service.get_vulnerabilities(
        project_id=project_id,
        round_id=round_id,
        severity=severity,
        status=status,
    )
