const pages = {
  mypage: {
    title: "마이페이지",
    description: "내 정보와 계정을 관리하는 공간입니다.",
    notice:
      "계정 관리 기능을 준비하고 있어요. 저장한 이슈와 종목은 보관함에서 확인할 수 있습니다.",
    links: [
      ["/saved", "보관함 보기"],
      ["/login", "로그인 페이지"],
      ["/signup", "회원가입 페이지"],
    ],
  },
  login: {
    title: "로그인",
    description: "WikiPulse 계정으로 돌아오는 곳입니다.",
    notice:
      "로그인 기능을 준비하고 있어요. 지금도 펄스맵과 이슈, 종목을 자유롭게 탐색할 수 있습니다.",
    links: [
      ["/pulse", "펄스맵 탐색하기"],
      ["/signup", "회원가입 페이지"],
    ],
  },
  signup: {
    title: "회원가입",
    description: "WikiPulse 계정을 만드는 곳입니다.",
    notice:
      "회원가입 기능을 준비하고 있어요. 아직 계정 정보는 입력하거나 저장할 수 없습니다.",
    links: [
      ["/pulse", "펄스맵 탐색하기"],
      ["/login", "로그인 페이지"],
    ],
  },
};

export default function AccountPage({ page }) {
  const { title, description, notice, links } = pages[page];
  return (
    <div className="wp-page account-page">
      <header className="wp-page-header">
        <div>
          <h1>{title}</h1>
          <p className="wp-subtitle">{description}</p>
        </div>
      </header>
      <section aria-label={`${title} 안내`}>
        <h2>준비 중입니다</h2>
        <p className="wp-subtitle">{notice}</p>
        <nav className="account-page__links" aria-label={`${title} 관련 메뉴`}>
          {links.map(([path, label], index) => (
            <a
              key={path}
              className="wp-button"
              data-variant={index === 0 ? "primary" : undefined}
              href={`#${path}`}
            >
              {label}
            </a>
          ))}
        </nav>
      </section>
    </div>
  );
}
