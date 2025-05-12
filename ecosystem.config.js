module.exports = {
    apps: [{
        name: 'PROJECT_NAME',
        script: 'python3.11',
        args: '-m src.PROJECT_NAME',
        watch: '.',
        env: {
            NODE_ENV: 'development'
        },
        env_production: {
            NODE_ENV: 'production'
        }
    }, {
        script: './service-worker/',
        watch: ['./service-worker']
    }],

    deploy: {
        production: {
            user: 'ubuntu',
            host: process.env.AWSIP || 'ENTER_AWS_IP_HERE',
            ref: 'origin/prod',
            repo: 'git@github.com:danedens/PROJECT_NAME.git',
            path: '/home/ubuntu/PROJECT_NAME',
            'pre-deploy-local': 'whoami',
            'post-deploy': 'pm2 restart PROJECT_NAME',
            'pre-setup': ''
        },
        development: {
            user: process.env.USER,
            host: 'localhost',
            repo: 'git@github.com:danedens/PROJECT_NAME.git',
            path: '/Users/d.edens/lab/madness_interactive/projects/python/PROJECT_NAME',
            'post-deploy': 'pip install -r requirements.txt && pm2 reload ecosystem.config.js --env development',
            'pre-setup': ''
        }
    }
};
