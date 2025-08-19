// blog-service/static/js/app.js
document.addEventListener('DOMContentLoaded', () => {
    const mainContent = document.getElementById('main-content');
    const authStatus = document.getElementById('auth-status');

    // 라우터 설정
    const routes = {
        '/': 'post-list-template',
        '/login': 'login-template',
        '/signup': 'signup-template',
        '/posts/:id': 'post-detail-template'
    };

    const renderTemplate = (templateId, container) => {
        const template = document.getElementById(templateId);
        if (template) {
            container.innerHTML = '';
            container.appendChild(template.content.cloneNode(true));
        }
    };

    const router = async () => {
        const path = window.location.hash.slice(1) || '/';
        let view, params;

        if (path.startsWith('/posts/')) {
            view = routes['/posts/:id'];
            params = { id: path.split('/')[2] };
        } else {
            view = routes[path];
        }

        if (view) {
            renderTemplate(view, mainContent);
            await activateView(path, params);
        }
    };

    // 뷰 활성화 로직
    const activateView = async (path, params) => {
        updateAuthStatus();
        if (path === '/') {
            await loadPosts();
        } else if (path.startsWith('/posts/')) {
            await loadPostDetail(params.id);
        } else if (path === '/login') {
            setupLoginForm();
        } else if (path === '/signup') {
            setupSignupForm();
        }
    };

    // 인증 관련
    const updateAuthStatus = () => {
        const token = sessionStorage.getItem('authToken');
        if (token) {
            authStatus.innerHTML = '<a href="#/" id="logout-btn">로그아웃</a>';
            document.getElementById('logout-btn').addEventListener('click', (e) => {
                e.preventDefault();
                sessionStorage.removeItem('authToken');
                window.location.hash = '/';
            });
        } else {
            authStatus.innerHTML = '<a href="#/login">로그인</a>';
        }
    };

    const setupLoginForm = () => {
        const form = document.getElementById('login-form');
        document.getElementById('go-to-signup').addEventListener('click', () => {
            window.location.hash = '/signup';
        });
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const errorEl = document.getElementById('login-error');

            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                const data = await response.json();
                if (response.ok) {
                    sessionStorage.setItem('authToken', data.token);
                    window.location.hash = '/';
                } else {
                    errorEl.textContent = data.error || '로그인 실패';
                }
            } catch (err) {
                errorEl.textContent = '서버와 통신할 수 없습니다.';
            }
        });
    };

    // 회원가입 폼 처리
    const setupSignupForm = () => {
        const form = document.getElementById('signup-form');
        document.getElementById('go-to-login').addEventListener('click', () => {
            window.location.hash = '/login';
        });
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            // [수정] 회원가입 폼의 고유 ID를 사용
            const username = document.getElementById('signup-username').value;
            const password = document.getElementById('signup-password').value;
            const errorEl = document.getElementById('signup-error');

            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                const data = await response.json();
                if (response.ok) {
                    alert('회원가입 성공! 로그인 페이지로 이동합니다.');
                    window.location.hash = '/login';
                } else {
                    errorEl.textContent = data.error || '회원가입 실패';
                }
            } catch (err) {
                errorEl.textContent = '서버와 통신할 수 없습니다.';
            }
        });
    };

    // 데이터 로딩
    const loadPosts = async () => {
        try {
            const response = await fetch('/api/posts');
            if (!response.ok) throw new Error('Network response was not ok');
            const posts = await response.json();
            const container = document.getElementById('posts-container');
            container.innerHTML = '';
            posts.forEach(post => {
                const li = document.createElement('li');
                li.className = 'post-list-item';
                li.innerHTML = `
                    <h3><a href="#/posts/${post.id}">${post.title}</a></h3>
                    <p>by ${post.author}</p>
                `;
                container.appendChild(li);
            });
        } catch (err) {
            console.error('게시물을 불러오는 데 실패했습니다.', err);
            const container = document.getElementById('posts-container');
            if(container) container.innerHTML = '<p>게시물을 불러오는 데 실패했습니다.</p>';
        }
    };

    const loadPostDetail = async (id) => {
        try {
            const response = await fetch(`/api/posts/${id}`);
            if (!response.ok) throw new Error('Network response was not ok');
            const post = await response.json();
            const container = document.getElementById('post-detail-container');
            container.innerHTML = `
                <h2>${post.title}</h2>
                <p class="meta">by ${post.author}</p>
                <div class="content">${post.content.replace(/\n/g, '<br>')}</div>
            `;
        } catch (err) {
            console.error('게시물 상세 정보를 불러오는 데 실패했습니다.', err);
            const container = document.getElementById('post-detail-container');
            if(container) container.innerHTML = '<p>게시물 정보를 불러올 수 없습니다.</p>';
        }
    };

    // 초기화
    window.addEventListener('hashchange', router);
    router();
});