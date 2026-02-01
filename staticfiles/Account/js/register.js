document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("registerForm");
    const password = form.querySelector('input[name="password"]');
    const confirmPassword = form.querySelector('input[name="confirm_password"]');
    const errorMsg = document.getElementById("error");
    const registerBtn = document.getElementById("registerBtn");

    function validatePasswords() {
        if (!password.value || !confirmPassword.value) {
            registerBtn.disabled = true;
            errorMsg.style.display = "none";
            return;
        }

        if (password.value !== confirmPassword.value) {
            errorMsg.style.display = "block";
            registerBtn.disabled = true;
        } else {
            errorMsg.style.display = "none";
            registerBtn.disabled = false;
        }
    }

    password.addEventListener("input", validatePasswords);
    confirmPassword.addEventListener("input", validatePasswords);

    form.addEventListener("submit", function (e) {
        if (password.value !== confirmPassword.value) {
            e.preventDefault();
            confirmPassword.focus();
        }
    });

    validatePasswords(); // auto-run on page load to enable button if passwords match
});