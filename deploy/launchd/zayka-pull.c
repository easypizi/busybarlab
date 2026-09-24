#include <spawn.h>
#include <sys/wait.h>

extern char **environ;

/* /bin/bash started by launchd cannot read ~/Documents. This signed helper
   holds that permission, and the pull script runs as its child. */
int main(int argc, char **argv) {
    pid_t pid;
    char *child[3];
    int status = 0;
    int rc;

    if (argc < 2) {
        return 64;
    }
    child[0] = "/bin/bash";
    child[1] = argv[1];
    child[2] = NULL;
    rc = posix_spawn(&pid, "/bin/bash", NULL, NULL, child, environ);
    if (rc != 0) {
        return 127;
    }
    if (waitpid(pid, &status, 0) < 0) {
        return 127;
    }
    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    return 1;
}
