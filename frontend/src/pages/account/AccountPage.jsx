export default function AccountPage({ member }) {
  return (
    <div className="wp-page account-page">
      <header className="wp-page-header">
        <div>
          <h1>마이페이지</h1>
          <p className="wp-subtitle">내 정보와 저장한 관심사를 확인하세요.</p>
        </div>
      </header>
      <section aria-label="내 정보">
        <h2>{member.displayName}</h2>
        {member.email && <p className="wp-subtitle">{member.email}</p>}
        <nav className="account-page__links" aria-label="계정 관련 메뉴">
          <a className="wp-button" data-variant="primary" href="#/saved">
            보관함 보기
          </a>
        </nav>
      </section>
    </div>
  );
}
