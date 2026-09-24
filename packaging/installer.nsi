; installer.nsi -- ScreenshotQA 安装包 (NSIS 3.x, Unicode)
; 编译: makensis installer.nsi
; 说明: 每用户安装(免 UAC), 装到 %LOCALAPPDATA%\Programs\ScreenshotQA

Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 32

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!define APPNAME      "ScreenshotQA"
!define APPDISPLAY   "ScreenshotQA - 截图答题助手"
!define APPVERSION   "1.2.0"
!define EXE          "ScreenshotQA.exe"
!define REGKEY       "Software\ScreenshotQA"
!define UNINSTKEY    "Software\Microsoft\Windows\CurrentVersion\Uninstall\ScreenshotQA"
!define RUNKEY       "Software\Microsoft\Windows\CurrentVersion\Run"

Name "${APPDISPLAY} ${APPVERSION}"
Caption "${APPDISPLAY} ${APPVERSION} 安装向导"
BrandingText "${APPDISPLAY}"

OutFile "dist\ScreenshotQA-Setup-${APPVERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
InstallDirRegKey HKCU "${REGKEY}" "InstallDir"
RequestExecutionLevel user
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "1.2.0.0"
VIAddVersionKey /LANG=2052 "ProductName"     "${APPDISPLAY}"
VIAddVersionKey /LANG=2052 "FileDescription" "ScreenshotQA 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion"     "${APPVERSION}"
VIAddVersionKey /LANG=2052 "ProductVersion"  "${APPVERSION}"
VIAddVersionKey /LANG=2052 "LegalCopyright"  "MIT License"

; --------------------------------------------------------------------------- ;
; 界面
; --------------------------------------------------------------------------- ;
!define MUI_ICON   "app.ico"
!define MUI_UNICON "app.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "安装 ${APPDISPLAY} ${APPVERSION}"
!define MUI_WELCOMEPAGE_TEXT  "这个程序会装好一个常驻后台的截图工具:$\r$\n$\r$\n  · 按 F8 = 开始/停止「每 5 秒自动截取屏幕固定区域」$\r$\n  · 按 F9 = 手动截取整屏$\r$\n  · 截图默认存到 D:\screenshots, 可用开始菜单里的「设置保存位置」随时改成别的文件夹$\r$\n  · 最新一张始终写一份 latest.png(AI/MCP 读这个固定文件名)$\r$\n$\r$\n配合 WorkBuddy 等 AI 工具读取 latest.png 即可自动答题。$\r$\n$\r$\n安装不需要管理员权限, 只装到当前用户目录。$\r$\n$\r$\n点「下一步」继续。"

!define MUI_DIRECTORYPAGE_TEXT_TOP "安装到下面的文件夹(建议保持默认, 装在这里不需要管理员权限):"
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!define MUI_FINISHPAGE_RUN_TEXT "立即启动 ScreenshotQA(启动后按 F8 开始自动截图)"
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_SHOWREADME_TEXT "设置截图保存位置"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION LaunchSettings
!define MUI_FINISHPAGE_LINK "查看使用说明(README)"
!define MUI_FINISHPAGE_LINK_LOCATION "$INSTDIR\README.txt"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; --------------------------------------------------------------------------- ;
; 文案
; --------------------------------------------------------------------------- ;
LangString DESC_SEC_MAIN    ${LANG_SIMPCHINESE} "程序本体(必需)。"
LangString DESC_SEC_SM      ${LANG_SIMPCHINESE} "在开始菜单建立快捷方式: 启动、标定截图区域、设置保存位置、打开目录、打开日志、打开设置。"
LangString DESC_SEC_DESKTOP ${LANG_SIMPCHINESE} "在桌面建立一个启动快捷方式。"
LangString DESC_SEC_AUTORUN ${LANG_SIMPCHINESE} "开机后自动在后台启动(无窗口), 登录即可用 F8 开关自动截图。"
LangString DESC_SEC_IMPORT  ${LANG_SIMPCHINESE} "如果检测到旧版源码目录的标定结果(D:\screenshot-qa\region_config.json), 直接导入, 不用重新标定。"

; --------------------------------------------------------------------------- ;
; 安装
; --------------------------------------------------------------------------- ;
Function .onInit
  ; 已安装过就预填原目录
  ReadRegStr $0 HKCU "${REGKEY}" "InstallDir"
  ${If} $0 != ""
    StrCpy $INSTDIR $0
  ${EndIf}
FunctionEnd

Section "ScreenshotQA 主程序" SEC_MAIN
  SectionIn RO
  SetOutPath "$INSTDIR"
  SetOverwrite try
  ; 程序本体 (PyInstaller onedir: ScreenshotQA.exe + _internal\*)
  ; 不用 onefile: 本机实测 onefile + tkinter 退出要 ~25s
  File /r "dist\ScreenshotQA\*.*"
  File "app.ico"
  File "README.txt"
  File "..\region_config.default.json"

  WriteRegStr HKCU "${REGKEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${REGKEY}" "Version" "${APPVERSION}"

  ; 卸载信息(控制面板)
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayName"     "${APPDISPLAY}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion"  "${APPVERSION}"
  WriteRegStr HKCU "${UNINSTKEY}" "Publisher"       "ScreenshotQA"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon"     "$INSTDIR\${EXE}"
  WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${UNINSTKEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINSTKEY}" "EstimatedSize" "$0"

  ; 初始化数据目录与默认配置(不覆盖已存在的)
  CreateDirectory "$APPDATA\${APPNAME}"
  CreateDirectory "D:\screenshots"
  ${IfNot} ${FileExists} "$APPDATA\${APPNAME}\region_config.json"
    SetOutPath "$APPDATA\${APPNAME}"
    File "/oname=region_config.json" "..\region_config.default.json"
  ${EndIf}
  SetOutPath "$INSTDIR"
SectionEnd

Section "开始菜单快捷方式" SEC_SM
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortCut "$SMPROGRAMS\${APPNAME}\启动 ScreenshotQA.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\app.ico" 0 SW_SHOWNORMAL "" "启动监听(F8=自动截图开关)"
  CreateShortCut "$SMPROGRAMS\${APPNAME}\标定截图区域.lnk"      "$INSTDIR\${EXE}" "calibrate" "$INSTDIR\app.ico" 0
  CreateShortCut "$SMPROGRAMS\${APPNAME}\设置保存位置.lnk"      "$INSTDIR\${EXE}" "settings" "$INSTDIR\app.ico" 0
  CreateShortCut "$SMPROGRAMS\${APPNAME}\立即抓一张.lnk"        "$INSTDIR\${EXE}" "shot" "$INSTDIR\app.ico" 0
  CreateShortCut "$SMPROGRAMS\${APPNAME}\打开截图目录.lnk"      "$INSTDIR\${EXE}" "dir" "$INSTDIR\app.ico" 0
  CreateShortCut "$SMPROGRAMS\${APPNAME}\查看运行日志.lnk"      "$INSTDIR\${EXE}" "logs" "$INSTDIR\app.ico" 0
  CreateShortCut "$SMPROGRAMS\${APPNAME}\打开设置文件.lnk"      "$INSTDIR\${EXE}" "config" "$INSTDIR\app.ico" 0
  CreateShortCut "$SMPROGRAMS\${APPNAME}\热键自检.lnk"          "$INSTDIR\${EXE}" "hotkey f8" "$INSTDIR\app.ico" 0
  CreateShortCut "$SMPROGRAMS\${APPNAME}\使用说明.lnk"          "$INSTDIR\README.txt"
  CreateShortCut "$SMPROGRAMS\${APPNAME}\卸载 ScreenshotQA.lnk" "$INSTDIR\uninstall.exe"
SectionEnd

Section "桌面快捷方式" SEC_DESKTOP
  CreateShortCut "$DESKTOP\ScreenshotQA.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\app.ico" 0 SW_SHOWNORMAL "" "按 F8 开始/停止自动截图"
SectionEnd

Section "开机自动启动(后台静默)" SEC_AUTORUN
  WriteRegStr HKCU "${RUNKEY}" "${APPNAME}" '"$INSTDIR\${EXE}" run --hide'
SectionEnd

Section "导入旧版标定结果(如有)" SEC_IMPORT
  ${If} ${FileExists} "D:\screenshot-qa\region_config.json"
    CopyFiles /SILENT "D:\screenshot-qa\region_config.json" "$APPDATA\${APPNAME}\region_config.json"
    DetailPrint "已导入 D:\screenshot-qa\region_config.json 的标定结果"
  ${Else}
    DetailPrint "未发现旧版配置, 跳过(启动后用「标定截图区域」拖一次框即可)"
  ${EndIf}
SectionEnd

; --------------------------------------------------------------------------- ;
; 说明文字
; --------------------------------------------------------------------------- ;
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_MAIN}    $(DESC_SEC_MAIN)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_SM}      $(DESC_SEC_SM)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP} $(DESC_SEC_DESKTOP)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_AUTORUN} $(DESC_SEC_AUTORUN)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_IMPORT}  $(DESC_SEC_IMPORT)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function LaunchApp
  Exec '"$INSTDIR\${EXE}"'
FunctionEnd

Function LaunchSettings
  Exec '"$INSTDIR\${EXE}" settings'
FunctionEnd

; --------------------------------------------------------------------------- ;
; 卸载
; --------------------------------------------------------------------------- ;
Var /GLOBAL keepShots

Function un.onInit
  ; 静默卸载(/S)时默认【不】删除截图 —— 防止误删用户数据
  MessageBox MB_YESNO|MB_ICONQUESTION \
    "是否同时删除截图目录 D:\screenshots 里的所有图片?$\r$\n$\r$\n选「否」= 只卸载程序, 保留截图与配置。" \
    /SD IDNO IDYES del_shots IDNO keep_shots
  del_shots:
    StrCpy $keepShots "0"
    Goto done_un_init
  keep_shots:
    StrCpy $keepShots "1"
  done_un_init:
FunctionEnd

Section "Uninstall"
  ; 关掉正在运行的实例
  ExecWait 'taskkill /IM ${EXE} /F' $0

  ; 程序本体是 onedir 目录树, 整个删掉(NSIS 卸载器从 %TEMP% 副本运行, 不会被锁)
  Delete "$INSTDIR\${EXE}"
  Delete "$INSTDIR\app.ico"
  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\region_config.default.json"
  Delete "$INSTDIR\uninstall.exe"
  RMDir /r "$INSTDIR"

  ; 快捷方式
  Delete "$DESKTOP\ScreenshotQA.lnk"
  Delete "$SMPROGRAMS\${APPNAME}\*.lnk"
  RMDir "$SMPROGRAMS\${APPNAME}"

  ; 注册表
  DeleteRegKey HKCU "${REGKEY}"
  DeleteRegKey HKCU "${UNINSTKEY}"
  DeleteRegValue HKCU "${RUNKEY}" "${APPNAME}"

  ; 用户数据
  ${If} $keepShots == "0"
    RMDir /r "D:\screenshots"
    Delete "$APPDATA\${APPNAME}\region_config.json"
    Delete "$APPDATA\${APPNAME}\_capture.log"
  ${EndIf}
SectionEnd
