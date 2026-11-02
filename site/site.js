// SharePoint Navigator product page: language, the download button for the visitor's system, and
// the current version from GitHub. Works without this script too; it only improves the page.

const REPO = "yusungchang/sharepoint-navigator";
const DL = `https://github.com/${REPO}/releases/latest/download/`;

// Korean text for every element with data-t. English is in the HTML itself.
const KO = {
  "nav.features": "기능",
  "nav.setup": "설정",
  "nav.download": "다운로드",
  "hero.title": "SharePoint 저장 공간,<br>어디에 쓰이는지 보세요.",
  "hero.lead": "모든 사이트의 문서 라이브러리를 하나의 트리로 보고, 현재 파일과 버전 기록이 각각 얼마나 차지하는지 확인합니다. 모든 사이트에서 파일을 찾고 정리하세요. 내 컴퓨터에서 실행되는 작은 앱입니다.",
  "hero.download": "다운로드",
  "hero.setup": "관리자 설정",
  "b1.label": "내 컴퓨터에서 실행", "b1.sub": "Microsoft와만 통신",
  "b2.label": "모든 사이트를 한 번에", "b2.sub": "하나의 트리, 하나의 기준",
  "b3.label": "버전 기록 표시", "b3.sub": "되찾을 수 있는 공간",
  "b4.label": "모든 사이트 검색", "b4.sub": "찾은 다음 폴더로 바로",
  "b5.label": "한국어와 English", "b5.sub": "라이트와 다크",
  "b6.label": "무료 오픈 소스", "b6.sub": "MIT 라이선스",
  "features.title": "저장 공간을 알고, 정리하세요",
  "f1.title": "모든 사이트, 하나의 트리",
  "f1.text": "사이트마다 문서 라이브러리가 한 줄입니다. 열면 폴더가 200개씩 나타나고, 항목이 수만 개인 라이브러리도 바로 열립니다.",
  "f2.title": "현재 파일과 버전 기록",
  "f2.text": "막대마다 지금의 파일과 SharePoint가 보관하는 이전 버전으로 나눠 보여 줍니다. 모든 줄이 같은 기준이라 큰 폴더가 한눈에 보입니다.",
  "f3.title": "모든 사이트를 한 번에 검색",
  "f3.text": "사이트, 종류, 크기, 날짜로 거르고, 크기순으로 정렬해 조직 전체에서 가장 큰 파일을 찾습니다.",
  "f4.title": "이름 바꾸기, 복사, 이동",
  "f4.text": "먼저 미리 보고, 그사이 누가 바꾸지 않았는지 확인한 뒤 실행합니다. 복사는 덮어쓰지 않습니다.",
  "f5.title": "이전 버전 정리",
  "f5.text": "SharePoint가 제공하는 세 가지 규칙 그대로. 사이트의 마지막 정리 기록, 이름 입력 확인, 중지 버튼까지.",
  "f6.title": "서버에 설치할 것 없음",
  "f6.text": "PowerShell도, 스크립트도, 에이전트도 필요 없습니다. 앱 하나, Microsoft 로그인 한 번. 탭을 닫으면 앱도 멈춥니다.",
  "search.title": "찾고, 어디 있는지 바로 보기",
  "search.text": "모든 사이트를 한 번에 검색합니다. <b>트리에서 보기</b>를 누르면 결과까지 폴더를 차례로 열고 강조해서, 이름 바꾸기나 이동, 폴더 크기 확인이 한 번의 클릭 거리입니다.",
  "sec.title": "조심스럽게 만들었습니다",
  "sec.sub": "조직의 파일을 다루는 앱이라, 지루할 만큼 신중하게 동작합니다.",
  "sec.c1": "내 컴퓨터에서 실행되고 Microsoft와만 통신합니다. 별도 서버도, 원격 수집도, 가입도 없습니다.",
  "sec.c2": "로그인한 사람이 열 수 있는 것만 보입니다. 로그인 정보는 시스템의 보호된 저장소(키체인 또는 Windows)에 보관합니다.",
  "sec.c3": "변경 전에 항목을 다시 확인하고, 덮어쓰지 않습니다. 복사와 이동은 같은 라이브러리 안에서만 합니다.",
  "sec.c4": "버전 정리를 시작하면 SharePoint에 기록된 내용과 바로 비교하고, 다르면 즉시 중지합니다.",
  "sec.c5": "폴더를 열면 그 폴더만 읽습니다. 몰래 테넌트 전체를 훑지 않습니다.",
  "setup.title": "조직마다 한 번만 설정",
  "setup.sub": "Microsoft 365 관리자가 작은 Entra 앱을 등록합니다. 5분 정도 걸리고 비밀 키는 필요 없습니다.",
  "setup.s1": "Entra 관리 센터에서 <b>앱 등록 → 새 등록</b>. 단일 테넌트, 리디렉션 URI 없음.",
  "setup.s2": "<b>인증</b>에서 <b>퍼블릭 클라이언트 흐름 허용</b>을 켭니다.",
  "setup.s3": "위임된 권한 추가: Microsoft Graph <code>Sites.Read.All</code>, <code>Sites.ReadWrite.All</code>, SharePoint <code>AllSites.Read</code>, 정리용 <code>AllSites.FullControl</code>. 관리자 동의를 부여합니다.",
  "setup.s4": "사용자에게 <b>애플리케이션(클라이언트) ID</b>를 알려 주세요. 앱이 처음 한 번 테넌트 이름과 함께 묻습니다.",
  "setup.note": "팁: ID를 담은 <code>contoso_clientid.txt</code> 파일을 앱 옆에 두면 직원은 아무것도 입력하지 않습니다. 전체 사이트 목록과 정리에는 SharePoint 관리자 역할이 필요합니다.",
  "setup.more": "단계별 안내 보기",
  "download.title": "다운로드",
  "download.sub": "macOS와 Windows용 무료 앱입니다. SharePoint Online이 포함된 Microsoft 365가 필요합니다.",
  "dl.mac": "Apple 실리콘 (M1 이후)",
  "dl.macNote": "Intel Mac은 소스에서 실행하세요 (GitHub 참고).",
  "dl.win": "Windows 10, 11 (.zip)",
  "dl.winNote": "64비트. 설치 없이 압축을 풀고 실행합니다.",
  "dl.sourceTitle": "소스에서 실행",
  "dl.source": "Python 3.11 이상",
  "dl.sourceNote": "Intel을 포함한 모든 Mac, Windows, 브라우저가 있는 Linux.",
  "first.title": "처음 실행할 때",
  "first.mac1": "압축을 풀고 <b>sharepoint-navigator</b>를 두 번 클릭하세요.",
  "first.mac2": "확인할 수 없다는 창이 뜨면 <b>완료</b>를 누른 뒤, 시스템 설정 → 개인정보 보호 및 보안 → <b>그래도 열기</b>. 처음 한 번만입니다.",
  "first.both": "터미널 창에 로그인 코드가 나오고 브라우저가 열립니다. 앱을 쓰는 동안 그 창을 열어 두세요.",
  "first.win1": "zip 파일을 오른쪽 클릭 → <b>압축 풀기</b>, 그다음 <b>sharepoint-navigator.exe</b>를 두 번 클릭하세요.",
  "first.win2": "‘Windows의 PC 보호’ 창이 뜨면 <b>추가 정보</b> → <b>실행</b>을 누르세요.",
  "first.src1": "macOS: <code>sharepoint-navigator.command</code>를 두 번 클릭.",
  "first.src2": "그 외: <code>pip install -r requirements.txt</code> 후 <code>python sharepoint-navigator.py</code>.",
  "download.all": "모든 버전과 릴리스 노트",
  "nav.install": "설치",
  "inst.title": "설치, 업데이트, 제거",
  "inst.sub": "설치 프로그램도, 시스템에 남는 것도 없습니다. 앱 파일 하나와 사용자 폴더의 작은 설정 폴더뿐입니다.",
  "inst.install": "설치",
  "inst.uninstall": "제거",
  "inst.mac1": "다운로드한 파일의 압축을 풀고 <b>sharepoint-navigator</b>를 응용 프로그램 폴더(또는 원하는 폴더)로 옮기세요.",
  "inst.mac2": "선택: Dock으로 끌어 놓으면 한 번에 실행할 수 있습니다.",
  "inst.mac3": "<b>sharepoint-navigator</b>를 휴지통으로 옮기세요.",
  "inst.mac4": "Finder에서 이동 → 폴더로 이동, <code>~/.sharepoint-navigator</code>를 입력하고 그 폴더를 휴지통으로 옮기세요 (저장된 테넌트, 클라이언트 ID, 로그인).",
  "inst.mac5": "키체인 접근에서 <b>msal-extensions</b>를 검색해 그 항목을 삭제하세요 (암호화된 로그인 키).",
  "inst.win1": "zip 파일을 오른쪽 클릭 → <b>압축 풀기</b>. 문서\\SharePoint Navigator처럼 계속 둘 폴더에 푸세요.",
  "inst.win2": "선택: <b>sharepoint-navigator.exe</b>를 오른쪽 클릭 → <b>추가 옵션 표시</b> → <b>보내기</b> → <b>바탕 화면에 바로 가기 만들기</b>.",
  "inst.win3": "<b>sharepoint-navigator.exe</b>가 있는 폴더를 삭제하세요 (바로 가기를 만들었다면 그것도).",
  "inst.win4": "파일 탐색기 주소 표시줄에 <code>%USERPROFILE%\\.sharepoint-navigator</code>를 입력하고 그 폴더를 삭제하세요 (저장된 테넌트, 클라이언트 ID, 로그인).",
  "inst.updateTitle": "업데이트",
  "inst.up1": "새 버전을 받아 예전 파일과 바꾸세요.",
  "inst.up2": "테넌트, 클라이언트 ID, 로그인은 그대로라 바로 시작됩니다.",
  "inst.up3": "새 버전을 처음 열 때는 보안 단계가 한 번 더 나옵니다 (macOS는 그래도 열기, Windows는 실행).",
  "inst.up4": "다른 조직으로 바꾸려면 터미널에서 <code>--setup</code>을 붙여 실행하거나 설정 폴더를 삭제하세요.",
  "after.title": "다운로드가 시작됐습니다",
  "after.text": "아직 유료 인증서로 서명하지 않아서, 처음 열 때만 이렇게 해 주세요.",
  "after.close": "확인",
  "footer.text": "파일은 나와 Microsoft 사이에만 오갑니다.",
  "footer.source": "GitHub의 소스 코드",
  "footer.bug": "버그 신고",
  "footer.author": "만든 사람",
  "footer.tm": "SharePoint, Microsoft 365, Entra는 Microsoft의 상표입니다. 이 프로젝트는 Microsoft와 관련이 없습니다.",
};

const english = new Map();
document.querySelectorAll("[data-t]").forEach((e) => english.set(e, e.innerHTML));

// Screenshots: one per language and theme; <picture> picks light or dark from the system.
function showShots(lang) {
  const suffix = lang === "ko" ? "-ko" : "";
  for (const name of ["tree", "search"]) {
    document.getElementById(`shot-${name}`).src = `shots/${name}${suffix}.png`;
    document.getElementById(`shot-${name}-dark`).srcset = `shots/${name}${suffix}-dark.png`;
  }
}

function setLanguage(lang) {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-t]").forEach((e) => {
    e.innerHTML = lang === "ko" && KO[e.dataset.t] ? KO[e.dataset.t] : english.get(e);
  });
  document.getElementById("lang").textContent = lang === "ko" ? "EN" : "한국어";
  showShots(lang);
  try { localStorage.setItem("lang", lang); } catch { /* storage unavailable */ }
  showPlatform();
  showVersion();
}

// The visitor's system, from the browser. Apple silicon and Intel Macs can't be told apart
// reliably, so Macs get the Apple silicon download; Intel Macs are pointed to the source.
function platform() {
  const p = (navigator.userAgentData?.platform || navigator.platform || navigator.userAgent).toLowerCase();
  if (p.includes("win")) return "windows";
  if (p.includes("mac")) return "mac";
  return null;
}

function showPlatform() {
  const ko = document.documentElement.lang === "ko";
  const os = platform();
  const primary = document.getElementById("primary");
  const label = document.getElementById("primary-label");
  const choices = {
    mac: [DL + "SharePoint-Navigator-macOS-AppleSilicon.zip", ko ? "macOS용 다운로드" : "Download for macOS"],
    windows: [DL + "SharePoint-Navigator-Windows.zip", ko ? "Windows용 다운로드" : "Download for Windows"],
  };
  document.querySelectorAll(".platforms article").forEach((a) => a.classList.toggle("mine", a.id === os));
  if (os && choices[os]) {
    primary.href = choices[os][0];
    label.textContent = choices[os][1];
  }
}

// The newest published release, if there is one yet.
let release = null;
async function showVersion() {
  const el = document.getElementById("version");
  try {
    release = release || (await (await fetch(`https://api.github.com/repos/${REPO}/releases/latest`)).json());
    if (!release.tag_name) return;
    const ko = document.documentElement.lang === "ko";
    const date = new Date(release.published_at).toLocaleDateString(ko ? "ko-KR" : "en-US", { year: "numeric", month: "long", day: "numeric" });
    el.textContent = ko
      ? `버전 ${release.tag_name.replace(/^v/, "")} · ${date}`
      : `Version ${release.tag_name.replace(/^v/, "")} · ${date}`;
    el.hidden = false;
  } catch { /* offline or rate limited: the page works without it */ }
}

// Any download link: let the download start, then show the first-launch steps for that system.
// The steps are copied from the download card, so they are already in the visitor's language.
// One listener for the page, because the top button only gets its download link after load.
document.addEventListener("click", (e) => {
  const a = e.target.closest?.('a[href*="/releases/latest/download/"]');
  if (!a) return;
  const os = a.href.includes("macOS") ? "mac" : "windows";
  const steps = document.querySelector(`.steps[data-os="${os}"] ol`);
  const dialog = document.getElementById("after");
  if (!steps || !dialog.showModal) return;
  document.getElementById("after-steps").replaceChildren(steps.cloneNode(true));
  dialog.showModal();
});
document.getElementById("after").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) e.currentTarget.close();
});

document.getElementById("lang").addEventListener("click", () => setLanguage(document.documentElement.lang === "ko" ? "en" : "ko"));

// ?lang=ko or ?lang=en in the link wins, then the visitor's last choice, then the browser.
let initial = new URLSearchParams(location.search).get("lang");
if (initial !== "ko" && initial !== "en") {
  try { initial = localStorage.getItem("lang") || ""; } catch { initial = ""; }
}
if (!initial) initial = (navigator.languages || [navigator.language]).some((l) => /^ko/i.test(l)) ? "ko" : "en";
setLanguage(initial);
