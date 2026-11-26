// One tap into the public demo: fills the published demo password and signs in
// through the app's own sign-in form, so nothing about sign-in changes.
const PASSWORD = 'Fictional browser test password';

function enter() {
  const form = document.getElementById('login-form');
  const password = document.getElementById('password');
  const account = document.getElementById('account');
  if (!form || !password) return;
  if (account) account.value = '';
  password.value = PASSWORD;
  form.requestSubmit();
  // Start at the top of Home, not part-way down where the button was.
  window.scrollTo(0, 0);
  setTimeout(() => window.scrollTo(0, 0), 600);
}

for (const button of document.querySelectorAll('[data-demo-enter]')) {
  button.addEventListener('click', enter);
}
