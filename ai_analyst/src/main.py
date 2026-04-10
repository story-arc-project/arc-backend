from typing import Annotated
from src.individual import main as individual_main
from src.comprehensive import main as comprehensive_main
from src.resume import main as resume_main
from fastapi import Body, FastAPI

from src.models import ComprehensiveRequest, IndividualRequest, ResumeRequest

app = FastAPI()

@app.post("/individual")
async def individual(body: Annotated[IndividualRequest, Body()]):
    return individual_main(body.input)

@app.post("/comprehensive")
async def comprehensive(body: Annotated[ComprehensiveRequest, Body()]):
    return comprehensive_main(body.input, body.school, body.department)

@app.post("/resume")
async def resume(body: Annotated[ResumeRequest, Body()]):
    return resume_main(
        sources=body.sources,
        name_ko=body.name_ko,
        name_en=body.name_en,
        email=body.email,
        phone=body.phone,
        school=body.school,
        department=body.department,
        links=body.links,
        language=body.language,
        output_path=body.output_path,
        deep_crawl=body.deep_crawl
    )