*** Settings ***
Suite Setup    Remove Files  ${OUTPUT_DIR}/*.jp*g  ${OUTPUT_DIR}/*.png
Test Setup     Save Start Time
Test Teardown  Remove Files  ${OUTPUT_DIR}/*.jp*g  ${OUTPUT_DIR}/*.png
Resource       resources/common.robot

*** Variables ***
${BASENAME}  ${OUTPUTDIR}${/}screenshot
${FIRST_SCREENSHOT}  ${BASENAME}_1.png
${SECOND_SCREENSHOT}  ${BASENAME}_2.png
${FIRST_CUSTOM_SCREENSHOT}  ${OUTPUTDIR}${/}foo_1.png
${SECOND_CUSTOM_SCREENSHOT}  ${OUTPUTDIR}${/}foo_2.png
${PNG_CUSTOM_SCREENSHOT}  ${OUTPUTDIR}${/}foo.png
${JPG_CUSTOM_SCREENSHOT}  ${OUTPUTDIR}${/}foo.jpg

*** Test Cases ***
Screenshot Is Taken
    ${path}=  Take Screenshot and Verify  ${FIRST_SCREENSHOT}
    Should Be Equal  ${path}  ${FIRST_SCREENSHOT}

Each Screenshot Gets Separate Index
    Take Screenshot and Verify  ${FIRST_SCREENSHOT}
    Take Screenshot and Verify  ${FIRST_SCREENSHOT}  ${SECOND_SCREENSHOT}

Basename May Be Defined
    Repeat Keyword  2  Take Screenshot  foo
    Screenshots Should Exist  ${OUTPUTDIR}  ${FIRST_CUSTOM_SCREENSHOT}  ${SECOND_CUSTOM_SCREENSHOT}

Basename With Extension Turns Off Index Generation
    Repeat Keyword  3  Take Screenshot  xxx.jpg  jpg
    Repeat Keyword  2  Take Screenshot  yyy.jpeg  jpeg
    Screenshots Should Exist  ${OUTPUTDIR}  ${OUTPUTDIR}${/}xxx.jpg  ${OUTPUTDIR}${/}yyy.jpeg

Screenshot Width Can Be Given
    Take Screenshot  width=300px
    Screenshots Should Exist  ${OUTPUTDIR}  ${FIRST_SCREENSHOT}

Basename With Non-existing Directories Fails
    [Documentation]  FAIL Directory '${OUTPUTDIR}${/}non-existing' where to save the screenshot does not exist
    Take Screenshot  ${OUTPUTDIR}${/}non-existing${/}foo

Without Embedding
    Take Screenshot Without Embedding  no_embed.png

Png Screenshot Quality
    Compare Size  ${PNG_CUSTOM_SCREENSHOT}  png

Jpg Screenshot Quality
    Compare Size  ${JPG_CUSTOM_SCREENSHOT}  jpg

*** Keywords ***
Take Screenshot And Verify
    [Arguments]  @{expected files}
    ${path}=  Take Screenshot  format=png
    Screenshots Should Exist  ${OUTPUTDIR}  @{expected files}
    [Return]  ${path}

Compare Size
    [Arguments]  ${screenshot_name}  ${screenshot_format}
    Take Screenshot  ${screenshot_name}  ${screenshot_format}  quality=100
    ${high_quality_size}=  Get File Size  ${screenshot_name}
    Take Screenshot    ${screenshot_name}  ${screenshot_format}  quality=0
    ${low_quality_size}=  Get File Size  ${screenshot_name}
    ${decrease}=  Evaluate  ${high_quality_size} - ${low_quality_size}
    ${percentage_size_decrease}=  Evaluate  float(${decrease}) / float(${high_quality_size}) * 100
    Should Be True  ${percentage_size_decrease} > 50